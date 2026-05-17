import httpx
import json

BASE_URL = "http://localhost:8001"

print("=" * 70)
print("SECURE MESSENGER API TEST")
print("=" * 70)

# Test 1: Register a new user
print("\n[TEST 1] Registering new user 'testuser'...")
try:
    response = httpx.post(
        f"{BASE_URL}/register",
        json={"username": "testuser", "password": "test123"},
        timeout=10.0
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    register_data = response.json()
except Exception as e:
    print(f"ERROR: {e}")
    register_data = None

# Test 2: Login with those credentials
print("\n[TEST 2] Logging in with testuser credentials...")
token = None
try:
    response = httpx.post(
        f"{BASE_URL}/login",
        json={"username": "testuser", "password": "test123"},
        timeout=10.0
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    login_data = response.json()
    if "access_token" in login_data:
        token = login_data["access_token"]
        print(f"✓ Token obtained: {token[:20]}...")
except Exception as e:
    print(f"ERROR: {e}")
    login_data = None

# Test 3: Send a message from testuser to alice
if token:
    print("\n[TEST 3] Sending message from testuser to alice...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.post(
            f"{BASE_URL}/send",
            json={"recipient": "alice", "message": "Hello Alice, this is a test message!"},
            headers=headers,
            timeout=10.0
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        send_data = response.json()
    except Exception as e:
        print(f"ERROR: {e}")
else:
    print("\n[TEST 3] SKIPPED - No token available")

# Test 4: Get all messages
if token:
    print("\n[TEST 4] Getting all messages for testuser...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.get(
            f"{BASE_URL}/messages",
            headers=headers,
            timeout=10.0
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        messages_data = response.json()
        if isinstance(messages_data, list):
            print(f"✓ Retrieved {len(messages_data)} messages")
    except Exception as e:
        print(f"ERROR: {e}")
else:
    print("\n[TEST 4] SKIPPED - No token available")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
