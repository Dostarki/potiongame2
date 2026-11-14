# PotionRH
Original request: pull the repo and run it; later an isometric voxel island game. June 2026: add RainbowKit wallet login (Robinhood Chain mainnet only, mobile wallet deep-link), game starts with no characters, Market + Inventory with 6 character levels ($1/$10/$50/$100/$200/$400), card art based on the in-game characters, purchases saved in MongoDB. Then: when the island is full, offer a $2 island expansion.

User choices: purchases are DEMO (no payment taken), bought characters are placed on the island and work, same level can be bought many times, inventory is tied to the wallet and stored on the server.

## Architecture
- `/` -> `pages/GamePage.jsx`: iframe `public/game.html` (Three.js r160) + React overlay (main menu, bottom bar, Market/Inventory sheets). `/admin` admin panel.
- Wallet: `lib/wallet.js` (RainbowKit + wagmi, single chain id 4663), `hooks/useSession.js` (SIWE message via `viem/siwe`, JWT kept in localStorage per address, 7 days).
- React -> iframe via postMessage: `potion:state {placed[{id,level,slot}], potion, rate, plots, focus, focusPlot}`, `potion:focus {id}`; iframe -> React `potion:ready`.
- Backend `server.py`: `/api/auth/nonce`, `/api/auth/verify` (python `siwe`, chain 4663 only), `/api/game/catalog|state|buy|place|recall|expand`. Collections: `nonces` (TTL, marked used), `game_players` (potion, potion_at), `game_items` (one doc per purchase, placed/slot), `game_expansions`.
- Rules: LEVELS (price, per_min, max_placed 16/12/6/4/8/4), expansion $2, max 4, extras per expansion 4/4/2/1/2/1. Slot -> position mapping lives in game.html (`SLOTS`, `slotPos`, plots are 40x16 land strips on the south edge).

## Implemented
- Voxel island, potion tank, mines, Robinhood castle (earlier work). Ambient NPCs/machines removed: island starts empty.
- 2026-06: wallet login + chain lock, market, inventory, place/recall/find, server-side potion accrual, six unit models (miner, pump worker, small drill, big drill tower, hose extractor, factory), AI card art in `public/assets/cards`, island expansion plots. Backend 22/22 tests pass (`backend/tests/test_wallet_game.py`); UI checked by screenshots with an injected test provider.

- 2026-06: leaderboard. `GET /api/game/leaderboard` (player JWT) ranks wallets by characters owned, ties by island expansions; top 20 + caller's own row, addresses shortened server-side. UI: `LeaderboardPanel.jsx`, RANKS button in `GameHud`. Checked by curl + screenshot (desktop/mobile); no pytest added. Ranking currently includes wallets created by earlier automated tests.
- UI test tip: announce a stub provider via `eip6963:announceProvider` (rdns `test.wallet`) + JWT in localStorage; a plain `window.ethereum` stub gets stuck in the MetaMask SDK.

## Not real yet
- Payments are DEMO: buy/expand record `price_usd` + `demo: true`, no on-chain transfer.
- `REACT_APP_WALLETCONNECT_PROJECT_ID` is set (user supplied). Verified in headless browser: desktop QR renders, relay connects, mobile UA fires `metamask://connect` deep link. A full round-trip on a real phone (approve in wallet, return to browser) is NOT verified.
- Build fixes needed by the wallet libs: craco excludes `.cjs` from CRA asset rule, aliases RN async-storage to false, `qr` pinned to 0.5.5 in resolutions (0.7.x rejects border 0 and breaks the RainbowKit QR).

## Backlog
- P1: real on-chain payment (needs receiving address + token), tx verification on backend.
- P2: tap-to-place on the map, selling/upgrading characters.

## Known pitfalls
- Never `pip install siwe`. `signinwithethereum==5.1.0` already provides the `siwe` module; the PyPI `siwe==4.4.0` package overwrites it and crashes backend start with abnf 2.9.1 (all /api/* return 502). Fixed 2026-06 by removing it and re-freezing requirements.
