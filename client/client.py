"""
client.py — CLI client for Secure Messenger.

Run with:
    python -m client.client
"""

import getpass
import json
import threading

import httpx

BASE_URL = "http://localhost:8001"


def prompt_auth() -> tuple[str, str]:
    """Register or login. Returns (username, token)."""
    print("\n=== Secure Messenger ===", flush=True)
    print("1) Register\n2) Login", flush=True)
    choice = input("Choose (1/2): ").strip()

    username = input("Username: ").strip()
    password = input("Password: ").strip()

    if choice == "1":
        r = httpx.post(f"{BASE_URL}/register", json={"username": username, "password": password})
        if r.status_code != 201:
            print(f"Registration failed: {r.json().get('detail')}")
            return prompt_auth()
        print("Registered! Logging in...")

    r = httpx.post(f"{BASE_URL}/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"Login failed: {r.json().get('detail')}")
        return prompt_auth()

    return username, r.json()["access_token"]


def listen_for_messages(token: str, current_user: str) -> None:
    """Background thread: reads SSE stream and prints incoming messages."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.stream("GET", f"{BASE_URL}/stream", headers=headers, timeout=None) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    raw = line[len("data:"):].strip()
                    try:
                        msg = json.loads(raw.replace("'", '"'))
                        sender, recipient, content = msg["sender"], msg["recipient"], msg["content"]
                        if sender != current_user:
                            print(f"\n  [{sender} → {recipient}]: {content}\n  > ", end="", flush=True)
                    except Exception:
                        pass
    except Exception:
        print("\n[disconnected from server]")


def main():
    username, token = prompt_auth()
    print(f"\nWelcome, {username}!  (type your message and press Enter, or 'quit' to exit)")
    print("  Recipient: ", end="")
    recipient = input().strip()

    # Show message history
    headers = {"Authorization": f"Bearer {token}"}
    history = httpx.get(f"{BASE_URL}/messages", headers=headers)
    if history.status_code == 200:
        for m in history.json():
            print(f"  [{m['sender']} → {m['recipient']}]: {m['content']}")

    # Start SSE listener in background
    t = threading.Thread(target=listen_for_messages, args=(token, username), daemon=True)
    t.start()

    while True:
        try:
            content = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if content.lower() == "quit":
            break
        if not content:
            continue
        r = httpx.post(
            f"{BASE_URL}/messages",
            json={"content": content, "recipient": recipient},
            headers=headers,
        )
        if r.status_code != 201:
            print(f"  [error sending: {r.json().get('detail')}]")


if __name__ == "__main__":
    main()
