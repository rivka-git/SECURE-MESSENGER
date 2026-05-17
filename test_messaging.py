import httpx
import json

BASE_URL = 'http://localhost:8001'
client = httpx.Client()

print('=' * 60)
print('MESSAGING SYSTEM TEST')
print('=' * 60)

# 1. Register user1
print('\n[1] Registering user1...')
response = client.post(f'{BASE_URL}/register', json={'username': 'user1', 'password': 'password1'})
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')

# 2. Register user2
print('\n[2] Registering user2...')
response = client.post(f'{BASE_URL}/register', json={'username': 'user2', 'password': 'password2'})
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')

# 3. Login as user1
print('\n[3] Logging in as user1...')
response = client.post(f'{BASE_URL}/login', json={'username': 'user1', 'password': 'password1'})
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')
user1_token = None
if response.status_code == 200:
    user1_token = response.json().get('access_token')
    print(f'Token: {user1_token}')

# 4. Check if user2 exists
print('\n[4] Checking if user2 exists...')
headers = {'Authorization': f'Bearer {user1_token}'} if user1_token else {}
response = client.get(f'{BASE_URL}/users/user2', headers=headers)
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')

# 5. Send a message from user1 to user2
print('\n[5] Sending message from user1 to user2...')
headers = {'Authorization': f'Bearer {user1_token}'} if user1_token else {}
message_data = {'recipient': 'user2', 'content': 'Hello user2, this is a test message!'}
response = client.post(f'{BASE_URL}/send-message', json=message_data, headers=headers)
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')

# 6. Login as user2
print('\n[6] Logging in as user2...')
response = client.post(f'{BASE_URL}/login', json={'username': 'user2', 'password': 'password2'})
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')
user2_token = None
if response.status_code == 200:
    user2_token = response.json().get('access_token')
    print(f'Token: {user2_token}')

# 7. Get messages for user2
print('\n[7] Getting messages for user2...')
headers = {'Authorization': f'Bearer {user2_token}'} if user2_token else {}
response = client.get(f'{BASE_URL}/get-messages', headers=headers)
print(f'Status: {response.status_code}')
print(f'Response: {response.text}')
if response.status_code == 200:
    messages = response.json()
    print(f'\nTotal messages: {len(messages)}')
    for i, msg in enumerate(messages, 1):
        print(f'\nMessage {i}:')
        print(f'  From: {msg.get("sender")}')
        print(f'  Content: {msg.get("content")}')
        print(f'  Timestamp: {msg.get("timestamp")}')

print('\n' + '=' * 60)
print('TEST COMPLETE')
print('=' * 60)
