import sys, json, requests, datetime
from eth_account import Account
from eth_account.messages import encode_defunct
API = open('/app/frontend/.env').read().split('REACT_APP_BACKEND_URL=')[1].split()[0]
host = API.split('//')[1]
key = sys.argv[1] if len(sys.argv) > 1 else '0x' + '11'*32
chain = int(sys.argv[2]) if len(sys.argv) > 2 else 4663
acct = Account.from_key(key)
nonce = requests.get(f'{API}/api/auth/nonce', params={'address': acct.address}).json()['nonce']
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
msg = f"{host} wants you to sign in with your Ethereum account:\n{acct.address}\n\nSign in to PotionRH on Robinhood Chain.\n\nURI: {API}\nVersion: 1\nChain ID: {chain}\nNonce: {nonce}\nIssued At: {now}"
sig = Account.sign_message(encode_defunct(text=msg), key).signature.hex()
if not sig.startswith('0x'): sig = '0x' + sig
r = requests.post(f'{API}/api/auth/verify', json={'message': msg, 'signature': sig}, headers={'Origin': API})
print(json.dumps({'status': r.status_code, **r.json()}))
if '--replay' in sys.argv:
    print(requests.post(f'{API}/api/auth/verify', json={'message': msg, 'signature': sig}, headers={'Origin': API}).text)
