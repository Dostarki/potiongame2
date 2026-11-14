"""Backend tests for PotionRH wallet auth + /game/* endpoints."""
import os
import time
import datetime as dt
import secrets as pysecrets
import pytest
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # read from frontend/.env
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

HOST = BASE_URL.split("//", 1)[1]
CHAIN_ID = 4663
ADMIN_PASSWORD = "potion-admin-2026"


# ---------- SIWE helpers ----------

def build_siwe(address: str, nonce: str, chain_id: int = CHAIN_ID, domain: str = HOST, uri: str = BASE_URL) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n{address}\n\n"
        f"Sign in to PotionRH on Robinhood Chain.\n\n"
        f"URI: {uri}\nVersion: 1\nChain ID: {chain_id}\nNonce: {nonce}\nIssued At: {now}"
    )


def sign(msg: str, key: str) -> str:
    sig = Account.sign_message(encode_defunct(text=msg), key).signature.hex()
    return sig if sig.startswith("0x") else "0x" + sig


def new_wallet():
    key = "0x" + pysecrets.token_hex(32)
    acct = Account.from_key(key)
    return key, acct.address


def get_nonce(address: str):
    return requests.get(f"{BASE_URL}/api/auth/nonce", params={"address": address})


def login(key: str = None, address: str = None, chain_id: int = CHAIN_ID,
          domain: str = HOST, uri: str = BASE_URL, origin: str = None):
    if key is None:
        key, address = new_wallet()
    r = get_nonce(address)
    assert r.status_code == 200, r.text
    nonce = r.json()["nonce"]
    msg = build_siwe(address, nonce, chain_id=chain_id, domain=domain, uri=uri)
    sig = sign(msg, key)
    headers = {"Origin": origin if origin is not None else BASE_URL}
    return requests.post(f"{BASE_URL}/api/auth/verify", json={"message": msg, "signature": sig}, headers=headers), key, address, msg, sig


# ---------- Fixtures ----------

@pytest.fixture
def wallet_token():
    r, key, address, _, _ = login()
    assert r.status_code == 200, r.text
    return r.json()["token"], address


@pytest.fixture
def auth_headers(wallet_token):
    token, _ = wallet_token
    return {"Authorization": f"Bearer {token}"}


# ---------- Nonce ----------

class TestNonce:
    def test_nonce_valid(self):
        _, addr = new_wallet()
        r = get_nonce(addr)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["nonce"], str) and len(data["nonce"]) >= 16
        assert data["chain_id"] == CHAIN_ID

    def test_nonce_invalid_address(self):
        r = get_nonce("not-an-address")
        assert r.status_code == 422


# ---------- Verify / SIWE ----------

class TestVerify:
    def test_valid_login(self):
        r, _, address, _, _ = login()
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["address"] == address.lower()
        assert isinstance(data["token"], str) and len(data["token"]) > 20

    def test_wrong_chain_id(self):
        r, *_ = login(chain_id=1)
        assert r.status_code == 403

    def test_replayed_nonce(self):
        r, key, address, msg, sig = login()
        assert r.status_code == 200
        r2 = requests.post(f"{BASE_URL}/api/auth/verify",
                           json={"message": msg, "signature": sig},
                           headers={"Origin": BASE_URL})
        assert r2.status_code == 401

    def test_wrong_signature(self):
        key, address = new_wallet()
        r = get_nonce(address)
        nonce = r.json()["nonce"]
        msg = build_siwe(address, nonce)
        # sign with a different key
        bad_key = "0x" + pysecrets.token_hex(32)
        sig = sign(msg, bad_key)
        rv = requests.post(f"{BASE_URL}/api/auth/verify",
                           json={"message": msg, "signature": sig},
                           headers={"Origin": BASE_URL})
        assert rv.status_code == 401

    def test_domain_mismatch(self):
        # SIWE domain different from Origin header
        key, address = new_wallet()
        r = get_nonce(address)
        nonce = r.json()["nonce"]
        # build message with a different domain and uri
        msg = build_siwe(address, nonce, domain="evil.example.com", uri="https://evil.example.com")
        sig = sign(msg, key)
        rv = requests.post(f"{BASE_URL}/api/auth/verify",
                           json={"message": msg, "signature": sig},
                           headers={"Origin": BASE_URL})
        assert rv.status_code == 401


# ---------- Auth gating ----------

class TestAuthGating:
    def test_state_without_token(self):
        r = requests.get(f"{BASE_URL}/api/game/state")
        assert r.status_code == 401

    def test_admin_jwt_rejected_on_game(self):
        r = requests.post(f"{BASE_URL}/api/admin/login", json={"password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        admin_token = r.json()["token"]
        rg = requests.get(f"{BASE_URL}/api/game/state",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert rg.status_code == 403

    def test_catalog_public(self):
        r = requests.get(f"{BASE_URL}/api/game/catalog")
        assert r.status_code == 200
        data = r.json()
        cat = data["catalog"]
        assert len(cat) == 6
        prices = [c["price"] for c in sorted(cat, key=lambda x: x["level"])]
        assert prices == [1, 10, 50, 100, 200, 400]
        assert data["chain_id"] == CHAIN_ID
        assert data["demo"] is True


# ---------- Buy / Place / Recall ----------

class TestBuyPlaceRecall:
    def test_buy_persists_and_unknown_level(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/game/buy", json={"level": 1}, headers=auth_headers)
        assert r.status_code == 200, r.text
        s1 = r.json()
        unplaced = [i for i in s1["items"] if not i.get("placed") and i["level"] == 1]
        assert len(unplaced) >= 1
        assert unplaced[0]["price_usd"] == 1
        assert unplaced[0]["demo"] is True

        # buy again same level
        r2 = requests.post(f"{BASE_URL}/api/game/buy", json={"level": 1}, headers=auth_headers)
        assert r2.status_code == 200
        s2 = r2.json()
        assert len([i for i in s2["items"] if i["level"] == 1]) >= 2

        # persistence via GET state
        rs = requests.get(f"{BASE_URL}/api/game/state", headers=auth_headers)
        assert rs.status_code == 200
        assert len([i for i in rs.json()["items"] if i["level"] == 1]) >= 2

        # unknown level
        r3 = requests.post(f"{BASE_URL}/api/game/buy", json={"level": 99}, headers=auth_headers)
        assert r3.status_code == 422

    def test_place_nothing_to_place(self, auth_headers):
        # level 6 nothing bought yet
        r = requests.post(f"{BASE_URL}/api/game/place", json={"level": 6}, headers=auth_headers)
        assert r.status_code == 404

    def test_place_returns_focus(self, auth_headers):
        requests.post(f"{BASE_URL}/api/game/buy", json={"level": 2}, headers=auth_headers)
        r = requests.post(f"{BASE_URL}/api/game/place", json={"level": 2}, headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "focus" in data
        placed = [i for i in data["items"] if i["level"] == 2 and i.get("placed")]
        assert len(placed) == 1
        assert placed[0]["slot"] == 0

    def test_recall_and_recall_nothing(self, auth_headers):
        # recall when nothing placed for level 3
        r = requests.post(f"{BASE_URL}/api/game/recall", json={"level": 3}, headers=auth_headers)
        assert r.status_code == 404

        # buy, place, recall for level 3
        requests.post(f"{BASE_URL}/api/game/buy", json={"level": 3}, headers=auth_headers)
        rp = requests.post(f"{BASE_URL}/api/game/place", json={"level": 3}, headers=auth_headers)
        assert rp.status_code == 200
        rr = requests.post(f"{BASE_URL}/api/game/recall", json={"level": 3}, headers=auth_headers)
        assert rr.status_code == 200
        placed_now = [i for i in rr.json()["items"] if i["level"] == 3 and i.get("placed")]
        assert len(placed_now) == 0


# ---------- Expansion & capacity ----------

class TestExpansion:
    def test_fill_level_then_expand(self):
        # fresh wallet for isolation
        r, key, address, _, _ = login()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        # level 6 has max_placed=4. Buy 5, place 4, next place -> 409
        for _ in range(5):
            assert requests.post(f"{BASE_URL}/api/game/buy", json={"level": 6}, headers=h).status_code == 200
        for _ in range(4):
            assert requests.post(f"{BASE_URL}/api/game/place", json={"level": 6}, headers=h).status_code == 200
        r_full = requests.post(f"{BASE_URL}/api/game/place", json={"level": 6}, headers=h)
        assert r_full.status_code == 409

        # expand; capacity should grow by +1 for level 6
        re_ = requests.post(f"{BASE_URL}/api/game/expand", headers=h)
        assert re_.status_code == 200, re_.text
        data = re_.json()
        assert data["expansion"]["count"] == 1
        assert "focus_plot" in data
        cat_l6 = next(c for c in data["catalog"] if c["level"] == 6)
        assert cat_l6["max_placed"] == 4 + 1

        # should now place 5th item
        r_place = requests.post(f"{BASE_URL}/api/game/place", json={"level": 6}, headers=h)
        assert r_place.status_code == 200, r_place.text

    def test_max_expansions(self):
        r, key, address, _, _ = login()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        for i in range(4):
            resp = requests.post(f"{BASE_URL}/api/game/expand", headers=h)
            assert resp.status_code == 200, f"expand {i}: {resp.text}"
        # 5th should fail
        resp5 = requests.post(f"{BASE_URL}/api/game/expand", headers=h)
        assert resp5.status_code == 409

        # check catalog grew per-level
        state = requests.get(f"{BASE_URL}/api/game/state", headers=h).json()
        cat = {c["level"]: c["max_placed"] for c in state["catalog"]}
        base = {1: 16, 2: 12, 3: 6, 4: 4, 5: 8, 6: 4}
        extras = {1: 4, 2: 4, 3: 2, 4: 1, 5: 2, 6: 1}
        for lv in base:
            assert cat[lv] == base[lv] + 4 * extras[lv], f"level {lv}: {cat[lv]}"


# ---------- Potion accrual & isolation ----------

class TestPotion:
    def test_per_min_and_accrual(self):
        r, key, address, _, _ = login()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        # buy & place 1 of level 1 and 1 of level 2 -> per_min = 6+70 = 76
        requests.post(f"{BASE_URL}/api/game/buy", json={"level": 1}, headers=h)
        requests.post(f"{BASE_URL}/api/game/place", json={"level": 1}, headers=h)
        requests.post(f"{BASE_URL}/api/game/buy", json={"level": 2}, headers=h)
        requests.post(f"{BASE_URL}/api/game/place", json={"level": 2}, headers=h)
        s1 = requests.get(f"{BASE_URL}/api/game/state", headers=h).json()
        assert s1["per_min"] == 76
        potion1 = s1["potion"]
        time.sleep(3)
        s2 = requests.get(f"{BASE_URL}/api/game/state", headers=h).json()
        assert s2["potion"] > potion1

    def test_wallet_isolation(self):
        ra, _, addr_a, _, _ = login()
        rb, _, addr_b, _, _ = login()
        ha = {"Authorization": f"Bearer {ra.json()['token']}"}
        hb = {"Authorization": f"Bearer {rb.json()['token']}"}
        requests.post(f"{BASE_URL}/api/game/buy", json={"level": 4}, headers=ha)
        sa = requests.get(f"{BASE_URL}/api/game/state", headers=ha).json()
        sb = requests.get(f"{BASE_URL}/api/game/state", headers=hb).json()
        assert any(i["level"] == 4 for i in sa["items"])
        assert not any(i["level"] == 4 for i in sb["items"])
        assert sa["address"] == addr_a.lower()
        assert sb["address"] == addr_b.lower()


# ---------- Regression ----------

class TestRegression:
    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert r.json().get("message") == "Hello World"

    def test_settings(self):
        r = requests.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        data = r.json()
        for k in ("follow_url", "rt_url", "like_url", "share_url", "share_text"):
            assert k in data

    def test_admin_login(self):
        r = requests.post(f"{BASE_URL}/api/admin/login", json={"password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_admin_login_bad(self):
        r = requests.post(f"{BASE_URL}/api/admin/login", json={"password": "wrong"})
        assert r.status_code == 401
