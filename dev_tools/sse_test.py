import time, threading, json
import requests
from httpx import Client
BASE='http://127.0.0.1:8080'

# register users (ignore errors)
for u in [('alice','alicepass'),('bob','bobpass')]:
    try:
        requests.post(BASE+'/register', json={'username':u[0],'password':u[1]}).raise_for_status()
    except Exception:
        pass

# login
r=requests.post(BASE+'/login', json={'username':'alice','password':'alicepass'})
alice_token=r.json()['access_token']
r=requests.post(BASE+'/login', json={'username':'bob','password':'bobpass'})
bob_token=r.json()['access_token']
print('Tokens:', alice_token[:10]+'...', bob_token[:10]+'...')

# start SSE client for bob in background using httpx
messages=[]

def sse_listener():
    with Client(timeout=None) as c:
        with c.stream('GET', BASE+'/stream', headers={'Authorization':f'Bearer {bob_token}'}) as r:
            print('SSE status for bob', r.status_code)
            line_buf=''
            for chunk in r.iter_bytes():
                try:
                    chunk = chunk.decode('utf-8')
                except Exception:
                    continue
                line_buf += chunk
                while '\n' in line_buf:
                    line, line_buf = line_buf.split('\n',1)
                    if not line.strip():
                        continue
                    try:
                        data=json.loads(line)
                    except Exception:
                        print('raw line:', line)
                        continue
                    print('SSE bob got:', data)
                    messages.append(data)
                    if len(messages)>=1:
                        return

thr=threading.Thread(target=sse_listener, daemon=True)
thr.start()
# give SSE a moment
time.sleep(1)
# send message from alice to bob
h={'Content-Type':'application/json','Authorization':f'Bearer {alice_token}'}
body={'content':'hello bob','recipient':'bob','emoji':None}
r=requests.post(BASE+'/messages', json=body, headers=h)
print('POST /messages status', r.status_code, r.text[:200])
# wait for SSE
for i in range(6):
    if messages:
        break
    time.sleep(1)
print('messages received:', messages)
