# Test Credentials

Admin panel (/admin): password = potion-admin-2026 (from backend/.env ADMIN_PASSWORD)

Game login is by wallet signature (no password). For API tests generate any private key with eth_account and run
`python /app/tests/siwe_login.py <0xprivkey> 4663` to get a player JWT (Bearer token for /api/game/*).
UI tests: inject a `window.ethereum` stub (eth_accounts -> address, eth_chainId -> 0x1237) and put the JWT in
localStorage key `potion.session.<lowercase address>` before load.
