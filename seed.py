"""
seed.py — Populate the database with test users and messages.

Run with:
    python seed.py
"""

import httpx

BASE = "http://127.0.0.1:8001"

USERS = [
    ("alice", "alice123"),
    ("bob",   "bob12345"),
    ("charlie", "charlie1"),
]

MESSAGES = [
    ("alice",   "bob",     "Hey Bob, how are you?"),
    ("bob",     "alice",   "All good! You?"),
    ("alice",   "charlie", "Charlie, join the call later?"),
    ("charlie", "alice",   "Sure, what time?"),
    ("bob",     "charlie", "See you both at 5pm!"),
]


def register(username: str, password: str) -> None:
    r = httpx.post(f"{BASE}/register", json={"username": username, "password": password})
    if r.status_code == 201:
        print(f"  registered {username}")
    elif r.status_code == 400:
        print(f"  {username} already exists, skipping")
    else:
        print(f"  unexpected {r.status_code} for {username}: {r.text}")


def login(username: str, password: str) -> str:
    r = httpx.post(f"{BASE}/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def send(token: str, content: str, recipient: str) -> None:
    r = httpx.post(
        f"{BASE}/messages",
        json={"content": content, "recipient": recipient},
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 201:
        print(f"  sent: {content!r} → {recipient}")
    else:
        print(f"  failed to send: {r.text}")


if __name__ == "__main__":
    print("=== Seeding users ===")
    for username, password in USERS:
        register(username, password)

    print("\n=== Seeding messages ===")
    tokens = {u: login(u, p) for u, p in USERS}
    for sender, recipient, content in MESSAGES:
        send(tokens[sender], content, recipient)

    print("\nDone!")
