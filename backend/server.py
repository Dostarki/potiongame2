import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, APIRouter, Query, HTTPException, Depends, Request
from siwe import SiweMessage
from urllib.parse import urlparse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError
import os
import re
import secrets
import jwt
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR.parent / ".env")

# Connect on first use so `vercel build` can import this module before env vars exist.
client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global client, _db
    if _db is None:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            raise RuntimeError("MONGO_URL and DB_NAME must be set")
        client = AsyncIOMotorClient(mongo_url)
        _db = client[db_name]
    return _db

# One entry per collection: every field a route filters, sorts or dedupes on. Add the index in the same edit as the query.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("timestamp", DESCENDING)], name="timestamp_desc"),
    ],
    "players": [
        IndexModel([("nick_key", ASCENDING)], name="nick_key", unique=True),
        IndexModel([("last_seen", DESCENDING)], name="last_seen_desc"),
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
        IndexModel([("ref_code", ASCENDING)], name="ref_code", unique=True, partialFilterExpression={"ref_code": {"$type": "string"}}),
        IndexModel([("evm_key", ASCENDING)], name="evm_key", unique=True, partialFilterExpression={"evm_key": {"$type": "string"}}),
        IndexModel([("invites", DESCENDING)], name="invites_desc"),
    ],
    "settings": [
        IndexModel([("key", ASCENDING)], name="key", unique=True),
    ],
    "nonces": [
        IndexModel([("nonce", ASCENDING)], name="nonce", unique=True),
        IndexModel([("expires_at", ASCENDING)], name="expires_at_ttl", expireAfterSeconds=0),
    ],
    "game_players": [
        IndexModel([("address", ASCENDING)], name="address", unique=True),
    ],
    "game_expansions": [
        IndexModel([("address", ASCENDING), ("index", ASCENDING)], name="address_index", unique=True),
    ],
    "game_items": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("address", ASCENDING), ("bought_at", ASCENDING)], name="address_bought_at"),
        IndexModel([("address", ASCENDING), ("level", ASCENDING), ("slot", ASCENDING)], name="address_level_slot", unique=True, partialFilterExpression={"slot": {"$type": "int"}}),
    ],
}


async def ensure_indexes() -> None:
    database = get_db()
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await database[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logging.getLogger(__name__).error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    index_task = asyncio.create_task(ensure_indexes())
    yield
    index_task.cancel()
    with suppress(asyncio.CancelledError):
        await index_task
    if client is not None:
        client.close()


# Create the main app without a prefix
app = FastAPI(lifespan=lifespan)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await get_db().status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks(limit: int = Query(20, ge=1, le=100)):
    # Exclude MongoDB's _id field from the query results
    status_checks = await get_db().status_checks.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

NICK_RE = re.compile(r"^[A-Za-z0-9_]{2,12}$")
EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
REF_RE = re.compile(r"^PRH\d{5}$")
POINTS_PER_INVITE = 10
QUESTS = ("follow", "rt", "like", "share")
DEFAULT_SETTINGS = {
    "follow_url": "https://x.com/potionrh",
    "rt_url": "https://x.com/potionrh",
    "like_url": "https://x.com/potionrh",
    "share_url": "https://x.com/potionrh",
    "share_text": "Grabbing my potion at PotionRH 🧪",
}
JWT_ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)


def empty_progress() -> dict:
    return {q: False for q in QUESTS}


class PlayerCreate(BaseModel):
    nick: str
    evm_address: Optional[str] = None
    referral_code: Optional[str] = None


class Progress(BaseModel):
    follow: bool = False
    rt: bool = False
    like: bool = False
    share: bool = False


class Player(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    nick: str
    avatar_url: str
    visits: int
    created_at: str
    last_seen: str
    evm_address: Optional[str] = None
    ref_code: Optional[str] = None
    referred_by: Optional[str] = None
    invites: int = 0
    points: int = 0
    progress: Progress = Field(default_factory=Progress)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    follow_url: str
    rt_url: str
    like_url: str
    share_url: str
    share_text: str


class AdminLogin(BaseModel):
    password: str


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")


async def load_settings() -> dict:
    doc = await get_db().settings.find_one({"key": "main"}, {"_id": 0, "key": 0})
    return {**DEFAULT_SETTINGS, **(doc or {})}


def to_player(doc: dict) -> Player:
    invites = doc.get("invites", 0)
    return Player(**{**doc, "invites": invites, "points": invites * POINTS_PER_INVITE})


async def find_wallet_owner(evm_key: str) -> dict | None:
    return await get_db().players.find_one(
        {"$or": [
            {"evm_key": evm_key},
            {"evm_address": {"$regex": "^" + re.escape(evm_key) + "$", "$options": "i"}},
        ]},
        {"_id": 0, "nick_key": 1},
    )


async def ensure_ref_code(key: str) -> dict:
    while True:
        code = f"PRH{secrets.randbelow(100000):05d}"
        try:
            doc = await get_db().players.find_one_and_update(
                {"nick_key": key, "ref_code": {"$exists": False}},
                {"$set": {"ref_code": code}},
                return_document=ReturnDocument.AFTER,
                projection={"_id": 0},
            )
        except DuplicateKeyError:
            continue
        return doc or await get_db().players.find_one({"nick_key": key}, {"_id": 0})


@api_router.post("/players", response_model=Player)
async def register_player(input: PlayerCreate):
    nick = input.nick.strip().lstrip("@")
    if not NICK_RE.match(nick):
        raise HTTPException(status_code=422, detail="Username must be 2-12 letters, digits or _")
    key = nick.lower()
    now = datetime.now(timezone.utc).isoformat()
    evm_key = None
    if input.evm_address is not None:
        evm = input.evm_address.strip()
        if not EVM_RE.match(evm):
            raise HTTPException(status_code=422, detail="EVM address must be 0x followed by 40 hex characters")
        evm_key = evm.lower()
    ref = (input.referral_code or "").strip().upper()
    if ref:
        if not REF_RE.match(ref):
            raise HTTPException(status_code=422, detail="Referral code must look like PRH12345")
        referrer = await get_db().players.find_one({"ref_code": ref}, {"_id": 0, "nick_key": 1})
        if not referrer:
            raise HTTPException(status_code=422, detail="Referral code not found")
        if referrer["nick_key"] == key:
            raise HTTPException(status_code=422, detail="You cannot use your own code")
    existing = await get_db().players.find_one({"nick_key": key}, {"_id": 0})
    if evm_key:
        owner = await find_wallet_owner(evm_key)
        if owner and owner["nick_key"] != key:
            raise HTTPException(status_code=409, detail="Wallet already registered")
        if existing and existing.get("evm_address"):
            raise HTTPException(status_code=409, detail="Username already registered")
    if existing:
        updates = {"last_seen": now}
        if evm_key and not existing.get("evm_address"):
            updates["evm_address"] = evm_key
            updates["evm_key"] = evm_key
        try:
            doc = await get_db().players.find_one_and_update(
                {"nick_key": key},
                {"$set": updates, "$inc": {"visits": 1}},
                return_document=ReturnDocument.AFTER,
                projection={"_id": 0},
            )
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Wallet already registered")
    else:
        doc = {
            "id": str(uuid.uuid4()),
            "nick": nick,
            "nick_key": key,
            "avatar_url": f"https://unavatar.io/x/{key}",
            "created_at": now,
            "last_seen": now,
            "visits": 1,
            "invites": 0,
            "progress": empty_progress(),
        }
        if evm_key:
            doc["evm_address"] = evm_key
            doc["evm_key"] = evm_key
        try:
            await get_db().players.insert_one(doc)
        except DuplicateKeyError as exc:
            detail = "Wallet already registered" if "evm_key" in str(exc) else "Username already registered"
            raise HTTPException(status_code=409, detail=detail)
        doc.pop("_id", None)
    if not doc.get("ref_code"):
        doc = await ensure_ref_code(key)
    if ref and evm_key:
        claimed = await get_db().players.find_one_and_update(
            {"nick_key": key, "referred_by": {"$exists": False}},
            {"$set": {"referred_by": ref}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        if claimed:
            await get_db().players.update_one({"ref_code": ref}, {"$inc": {"invites": 1}})
            doc = claimed
    return to_player(doc)


@api_router.get("/allowlist")
async def allowlist():
    latest = await get_db().players.find({}, {"_id": 0, "nick": 1, "avatar_url": 1, "created_at": 1}).sort("created_at", -1).limit(10).to_list(10)
    top = await get_db().players.find({"invites": {"$gt": 0}}, {"_id": 0, "nick": 1, "avatar_url": 1, "ref_code": 1, "invites": 1}).sort([("invites", -1), ("created_at", 1)]).limit(10).to_list(10)
    for t in top:
        t["points"] = t["invites"] * POINTS_PER_INVITE
    return {"latest": latest, "leaders": top}


@api_router.get("/allowlist/count")
async def allowlist_count():
    return {"count": await get_db().players.count_documents({})}


@api_router.get("/allowlist/{nick}")
async def allowlist_find(nick: str):
    key = nick.lower().lstrip("@").strip()
    if not re.fullmatch(r"[a-z0-9_]{2,12}", key):
        raise HTTPException(status_code=422, detail="Enter a username")
    doc = await get_db().players.find_one(
        {"nick_key": key},
        {"_id": 0, "nick": 1, "avatar_url": 1, "created_at": 1, "ref_code": 1, "invites": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Not on the allow list")
    place = await get_db().players.count_documents({"created_at": {"$lt": doc.get("created_at", "")}}) + 1
    invites = doc.get("invites", 0)
    return {
        "nick": doc["nick"],
        "avatar_url": doc.get("avatar_url") or f"https://unavatar.io/x/{key}",
        "ref_code": doc.get("ref_code"),
        "points": invites * POINTS_PER_INVITE,
        "place": place,
    }


@api_router.get("/wallets/{address}")
async def wallet_taken(address: str):
    evm = address.strip()
    if not EVM_RE.match(evm):
        raise HTTPException(status_code=422, detail="EVM address must be 0x followed by 40 hex characters")
    if not await find_wallet_owner(evm.lower()):
        raise HTTPException(status_code=404, detail="Wallet not registered")
    return {"taken": True}


@api_router.get("/players/{nick}/invited")
async def invited_players(nick: str):
    key = nick.lower().lstrip("@").strip()
    doc = await get_db().players.find_one({"nick_key": key}, {"_id": 0, "ref_code": 1})
    if not doc or not doc.get("ref_code"):
        return {"invited": []}
    people = await get_db().players.find(
        {"referred_by": doc["ref_code"]},
        {"_id": 0, "nick": 1, "avatar_url": 1},
    ).sort("created_at", 1).limit(50).to_list(50)
    return {"invited": people}


@api_router.get("/players/{nick}", response_model=Player)
async def get_player(nick: str):
    doc = await get_db().players.find_one({"nick_key": nick.lower().lstrip("@")}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Player not found")
    return to_player(doc)


@api_router.patch("/players/{nick}/progress", response_model=Player)
async def update_progress(nick: str, input: Progress):
    done = {f"progress.{q}": True for q in QUESTS if getattr(input, q)}
    if not done:
        return await get_player(nick)
    doc = await get_db().players.find_one_and_update(
        {"nick_key": nick.lower().lstrip("@")},
        {"$set": {**done, "last_seen": datetime.now(timezone.utc).isoformat()}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Player not found")
    return to_player(doc)


@api_router.get("/settings", response_model=Settings)
async def get_settings():
    return Settings(**(await load_settings()))


@api_router.post("/admin/login")
async def admin_login(input: AdminLogin):
    if not secrets.compare_digest(input.password, os.environ["ADMIN_PASSWORD"]):
        raise HTTPException(status_code=401, detail="Wrong password")
    exp = datetime.now(timezone.utc) + timedelta(hours=12)
    token = jwt.encode({"role": "admin", "exp": exp}, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)
    return {"token": token}


@api_router.get("/admin/me", dependencies=[Depends(require_admin)])
async def admin_me():
    return {"role": "admin"}


@api_router.put("/admin/settings", response_model=Settings, dependencies=[Depends(require_admin)])
async def put_settings(input: Settings):
    await get_db().settings.update_one({"key": "main"}, {"$set": input.model_dump()}, upsert=True)
    return Settings(**(await load_settings()))


@api_router.get("/admin/players", response_model=List[Player], dependencies=[Depends(require_admin)])
async def admin_players(limit: int = Query(200, ge=1, le=1000)):
    docs = await get_db().players.find({}, {"_id": 0}).sort("last_seen", -1).limit(limit).to_list(limit)
    return [to_player(d) for d in docs]


CHAIN_ID = 4663
SESSION_DAYS = 7
LEVELS = {
    1: {"name": "Mine Worker", "price": 1, "per_min": 6, "max_placed": 16},
    2: {"name": "Pump Worker", "price": 10, "per_min": 70, "max_placed": 12},
    3: {"name": "Small Drill Rig", "price": 50, "per_min": 400, "max_placed": 6},
    4: {"name": "Big Drill Rig", "price": 100, "per_min": 900, "max_placed": 4},
    5: {"name": "Hose Extractor", "price": 200, "per_min": 2000, "max_placed": 8},
    6: {"name": "Potion Factory", "price": 400, "per_min": 4500, "max_placed": 4},
}


EXTRA_PER_EXPANSION = {1: 4, 2: 4, 3: 2, 4: 1, 5: 2, 6: 1}
EXPANSION_PRICE = 2
MAX_EXPANSIONS = 4


def capacity(level: int, expansions: int) -> int:
    return LEVELS[level]["max_placed"] + expansions * EXTRA_PER_EXPANSION[level]


class WalletVerify(BaseModel):
    message: str
    signature: str


class LevelInput(BaseModel):
    level: int


def require_player(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") != "player" or payload.get("chain_id") != CHAIN_ID or not payload.get("sub"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return payload["sub"]


@api_router.get("/auth/nonce")
async def wallet_nonce(address: str):
    if not EVM_RE.match(address):
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    nonce = secrets.token_hex(16)
    await get_db().nonces.insert_one({
        "nonce": nonce,
        "address": address.lower(),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    return {"nonce": nonce, "chain_id": CHAIN_ID}


@api_router.post("/auth/verify")
async def wallet_verify(input: WalletVerify, request: Request):
    try:
        msg = SiweMessage.from_message(input.message)
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed sign-in message")
    if msg.chain_id != CHAIN_ID:
        raise HTTPException(status_code=403, detail="Only Robinhood Chain mainnet is accepted")
    origin = request.headers.get("origin")
    site = urlparse(str(msg.uri))
    if site.netloc != msg.domain or (origin and urlparse(origin).netloc != msg.domain):
        raise HTTPException(status_code=401, detail="Sign-in message was issued for another site")
    address = str(msg.address).lower()
    row = await get_db().nonces.find_one_and_update(
        {"nonce": msg.nonce, "address": address, "used": {"$ne": True}, "expires_at": {"$gt": datetime.now(timezone.utc)}},
        {"$set": {"used": True}},
    )
    if not row:
        raise HTTPException(status_code=401, detail="Sign-in request expired, try again")
    try:
        msg.verify(signature=input.signature, domain=msg.domain, nonce=row["nonce"], chain_id=CHAIN_ID, timestamp=datetime.now(timezone.utc))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid wallet signature")
    now = datetime.now(timezone.utc)
    await get_db().game_players.update_one(
        {"address": address},
        {"$set": {"last_login": now.isoformat()}, "$setOnInsert": {"potion": 0.0, "potion_at": now.isoformat(), "created_at": now.isoformat()}},
        upsert=True,
    )
    token = jwt.encode(
        {"sub": address, "role": "player", "chain_id": CHAIN_ID, "exp": now + timedelta(days=SESSION_DAYS)},
        os.environ["JWT_SECRET"],
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "address": address}


def catalog(expansions: int = 0) -> list[dict]:
    return [{"level": lv, **spec, "max_placed": capacity(lv, expansions)} for lv, spec in LEVELS.items()]


async def count_expansions(address: str) -> int:
    return await get_db().game_expansions.count_documents({"address": address})


async def load_items(address: str) -> list[dict]:
    return await get_db().game_items.find({"address": address}, {"_id": 0, "address": 0}).sort("bought_at", 1).to_list(5000)


async def settle(address: str) -> float:
    """Bank the potion produced since the last change and return the current total."""
    now = datetime.now(timezone.utc)
    player = await get_db().game_players.find_one({"address": address}, {"_id": 0}) or {}
    placed = await get_db().game_items.find({"address": address, "placed": True}, {"_id": 0, "level": 1}).to_list(5000)
    per_sec = sum(LEVELS[i["level"]]["per_min"] for i in placed) / 60
    since = datetime.fromisoformat(player["potion_at"]) if player.get("potion_at") else now
    potion = float(player.get("potion", 0)) + per_sec * max(0.0, (now - since).total_seconds())
    await get_db().game_players.update_one(
        {"address": address},
        {"$set": {"potion": potion, "potion_at": now.isoformat()}, "$setOnInsert": {"created_at": now.isoformat()}},
        upsert=True,
    )
    return potion


async def game_state(address: str) -> dict:
    potion = await settle(address)
    items = await load_items(address)
    per_min = sum(LEVELS[i["level"]]["per_min"] for i in items if i.get("placed"))
    expansions = await count_expansions(address)
    return {
        "address": address, "potion": potion, "per_min": per_min, "items": items, "catalog": catalog(expansions),
        "expansion": {"count": expansions, "max": MAX_EXPANSIONS, "price": EXPANSION_PRICE}, "demo": True,
    }


@api_router.get("/game/catalog")
async def game_catalog():
    return {"catalog": catalog(), "chain_id": CHAIN_ID, "demo": True}


@api_router.get("/game/state")
async def get_game_state(address: str = Depends(require_player)):
    return await game_state(address)


@api_router.post("/game/buy")
async def buy_character(input: LevelInput, address: str = Depends(require_player)):
    spec = LEVELS.get(input.level)
    if not spec:
        raise HTTPException(status_code=422, detail="Unknown character level")
    await get_db().game_items.insert_one({
        "id": str(uuid.uuid4()),
        "address": address,
        "level": input.level,
        "name": spec["name"],
        "price_usd": spec["price"],
        "demo": True,
        "placed": False,
        "bought_at": datetime.now(timezone.utc).isoformat(),
    })
    return await game_state(address)


@api_router.post("/game/place")
async def place_character(input: LevelInput, address: str = Depends(require_player)):
    spec = LEVELS.get(input.level)
    if not spec:
        raise HTTPException(status_code=422, detail="Unknown character level")
    items = get_db().game_items
    for _ in range(5):
        item = await items.find_one({"address": address, "level": input.level, "placed": False}, {"_id": 0, "id": 1}, sort=[("bought_at", 1)])
        if not item:
            raise HTTPException(status_code=404, detail="Nothing in the inventory to place")
        used = {i["slot"] for i in await items.find({"address": address, "level": input.level, "placed": True}, {"_id": 0, "slot": 1}).to_list(100)}
        free = next((s for s in range(capacity(input.level, await count_expansions(address))) if s not in used), None)
        if free is None:
            raise HTTPException(status_code=409, detail=f"No free spot on the island for {spec['name']}")
        await settle(address)
        try:
            done = await items.update_one({"id": item["id"], "address": address, "placed": False}, {"$set": {"placed": True, "slot": free}})
        except DuplicateKeyError:
            continue
        if done.modified_count:
            return {**(await game_state(address)), "focus": item["id"]}
    raise HTTPException(status_code=409, detail="Could not place, try again")


@api_router.post("/game/expand")
async def expand_island(address: str = Depends(require_player)):
    for _ in range(3):
        index = await count_expansions(address)
        if index >= MAX_EXPANSIONS:
            raise HTTPException(status_code=409, detail="The island is already at its maximum size")
        try:
            await get_db().game_expansions.insert_one({
                "id": str(uuid.uuid4()),
                "address": address,
                "index": index,
                "price_usd": EXPANSION_PRICE,
                "demo": True,
                "bought_at": datetime.now(timezone.utc).isoformat(),
            })
        except DuplicateKeyError:
            continue
        return {**(await game_state(address)), "focus_plot": index}
    raise HTTPException(status_code=409, detail="Could not expand, try again")


LEADERBOARD_SIZE = 20


def short_address(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}"


@api_router.get("/game/leaderboard")
async def game_leaderboard(address: str = Depends(require_player)):
    count_by_address = [{"$group": {"_id": "$address", "n": {"$sum": 1}}}]
    characters = {r["_id"]: r["n"] async for r in get_db().game_items.aggregate(count_by_address)}
    expansions = {r["_id"]: r["n"] async for r in get_db().game_expansions.aggregate(count_by_address)}
    ranked = sorted(
        ({"address": a, "characters": characters.get(a, 0), "expansions": expansions.get(a, 0)} for a in characters.keys() | expansions.keys()),
        key=lambda r: (-r["characters"], -r["expansions"], r["address"]),
    )
    rows = [{"rank": i + 1, "wallet": short_address(r["address"]), "characters": r["characters"], "expansions": r["expansions"], "me": r["address"] == address} for i, r in enumerate(ranked)]
    me = next((r for r in rows if r["me"]), None)
    return {"leaders": rows[:LEADERBOARD_SIZE], "me": me, "total": len(rows), "max_expansions": MAX_EXPANSIONS}


@api_router.post("/game/recall")
async def recall_character(input: LevelInput, address: str = Depends(require_player)):
    item = await get_db().game_items.find_one({"address": address, "level": input.level, "placed": True}, {"_id": 0, "id": 1}, sort=[("slot", -1)])
    if not item:
        raise HTTPException(status_code=404, detail="Nothing placed for this level")
    await settle(address)
    await get_db().game_items.update_one({"id": item["id"], "address": address}, {"$set": {"placed": False}, "$unset": {"slot": ""}})
    return await game_state(address)


# Include the router in the main app
app.include_router(api_router)

_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)