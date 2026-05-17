"""
test_app.py — Stage 1 + Stage 2 test suite.

HOW TO RUN:
  pytest tests/ -v
"""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.main import app
from server.models import Base, get_db
from server.crypto import encrypt, decrypt


# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_messenger.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register_and_login(client, username="alice", password="secret123") -> str:
    client.post("/register", json={"username": username, "password": password})
    response = client.post("/login", json={"username": username, "password": password})
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. Authentication tests
# ===========================================================================

class TestAuthentication:

    def test_register_success(self, client):
        response = client.post("/register", json={"username": "alice", "password": "secret123"})
        assert response.status_code == 201

    def test_register_duplicate_username(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/register", json={"username": "alice", "password": "other-password"})
        assert response.status_code == 400

    def test_register_password_too_short(self, client):
        response = client.post("/register", json={"username": "alice", "password": "abc"})
        assert response.status_code == 422

    def test_login_success(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/login", json={"username": "alice", "password": "secret123"})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_wrong_password(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/login", json={"username": "alice", "password": "wrongpassword"})
        assert response.status_code == 401

    def test_login_unknown_user(self, client):
        response = client.post("/login", json={"username": "ghost", "password": "secret123"})
        assert response.status_code == 401

    def test_messages_require_token(self, client):
        response = client.get("/messages")
        assert response.status_code in (401, 403)

    def test_messages_reject_bad_token(self, client):
        response = client.get("/messages", headers={"Authorization": "Bearer fake-token"})
        assert response.status_code == 401

    def test_messages_accept_valid_token(self, client):
        token = register_and_login(client)
        response = client.get("/messages", headers=auth(token))
        assert response.status_code == 200


# ===========================================================================
# 2. Encryption tests
# ===========================================================================

class TestEncryption:

    def test_encrypt_is_not_plain_text(self):
        assert encrypt("hello world") != "hello world"

    def test_decrypt_round_trip(self):
        original = "this is a secret message"
        assert decrypt(encrypt(original)) == original

    def test_same_message_encrypts_differently_each_time(self):
        assert encrypt("hello") != encrypt("hello")

    def test_tampered_ciphertext_raises(self):
        blob = encrypt("original")
        tampered = blob[:-4] + "XXXX"
        with pytest.raises(Exception):
            decrypt(tampered)

    def test_messages_are_stored_encrypted(self, client):
        from server.models import Message
        token = register_and_login(client)
        plain = "secret note"
        client.post("/register", json={"username": "bob", "password": "secret456"})
        resp = client.post(
            "/messages",
            json={"content": plain, "recipient": "bob"},
            headers=auth(token),
        )
        assert resp.status_code == 201
        db = TestingSession()
        row = db.query(Message).first()
        db.close()
        assert row is not None
        assert row.ciphertext != plain
        assert decrypt(row.ciphertext) == plain


# ===========================================================================
# 3. Messaging tests
# ===========================================================================

class TestMessaging:

    def test_send_message_success(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        register_and_login(client, "bob", "secret456")
        response = client.post(
            "/messages",
            json={"content": "hello bob", "recipient": "bob"},
            headers=auth(alice_token),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "hello bob"
        assert data["sender"] == "alice"
        assert data["recipient"] == "bob"

    def test_get_messages_returns_decrypted(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        register_and_login(client, "bob", "secret456")
        client.post("/messages", json={"content": "hi bob", "recipient": "bob"}, headers=auth(alice_token))
        response = client.get("/messages", headers=auth(alice_token))
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        assert messages[0]["content"] == "hi bob"

    def test_user_sees_only_their_messages(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        bob_token   = register_and_login(client, "bob",   "secret456")
        charlie_token = register_and_login(client, "charlie", "secret789")

        client.post("/messages", json={"content": "from alice to bob", "recipient": "bob"}, headers=auth(alice_token))
        client.post("/messages", json={"content": "from charlie to bob", "recipient": "bob"}, headers=auth(charlie_token))
        client.post("/messages", json={"content": "from bob to alice", "recipient": "alice"}, headers=auth(bob_token))

        resp = client.get("/messages", headers=auth(alice_token))
        assert resp.status_code == 200
        msgs = resp.json()
        contents = {(m["sender"], m["recipient"], m["content"]) for m in msgs}
        assert ("alice", "bob", "from alice to bob") in contents
        assert ("bob", "alice", "from bob to alice") in contents
        assert all(not (m["sender"] == "charlie" and m["recipient"] == "bob") for m in msgs)


# ===========================================================================
# 4. SSE / Stream tests
# ===========================================================================

class TestSSE:

    def test_stream_rejects_no_token(self, client):
        """GET /stream without token → 401/403."""
        with client.stream("GET", "/stream") as r:
            assert r.status_code in (401, 403)

    def test_stream_rejects_bad_token(self, client):
        """GET /stream with invalid token → 401."""
        with client.stream("GET", "/stream", headers={"Authorization": "Bearer bad"}) as r:
            assert r.status_code == 401

    def test_sse_stream_receives_broadcast(self, client):
        """Connect to /stream, send a message, verify it arrives in the stream."""
        alice_token = register_and_login(client, "alice", "secret123")
        bob_token   = register_and_login(client, "bob",   "secret456")

        received = []

        with client.stream("GET", "/stream", headers=auth(alice_token)) as stream_resp:
            assert stream_resp.status_code == 200

            # Send a message from bob to alice while stream is open
            client.post(
                "/messages",
                json={"content": "hello alice", "recipient": "alice"},
                headers=auth(bob_token),
            )

            # Read one SSE event
            for line in stream_resp.iter_lines():
                if line.startswith("data:"):
                    received.append(line)
                    break  # got one event, stop

        assert len(received) == 1
        assert "hello alice" in received[0]

    def test_only_relevant_messages_arrive(self, client):
        """Alice's stream should NOT receive messages between bob and charlie."""
        alice_token   = register_and_login(client, "alice",   "secret123")
        bob_token     = register_and_login(client, "bob",     "secret456")
        charlie_token = register_and_login(client, "charlie", "secret789")

        received = []

        with client.stream("GET", "/stream", headers=auth(alice_token)) as stream_resp:
            assert stream_resp.status_code == 200

            # bob → charlie (alice should NOT see this)
            client.post(
                "/messages",
                json={"content": "secret between bob and charlie", "recipient": "charlie"},
                headers=auth(bob_token),
            )
            # bob → alice (alice SHOULD see this)
            client.post(
                "/messages",
                json={"content": "hi alice", "recipient": "alice"},
                headers=auth(bob_token),
            )

            for line in stream_resp.iter_lines():
                if line.startswith("data:"):
                    received.append(line)
                    break

        assert len(received) == 1
        assert "hi alice" in received[0]
        assert "secret between bob and charlie" not in received[0]

    def test_concurrent_clients_both_receive(self, client):
        """Two clients connected to /stream both receive a broadcast message."""
        alice_token = register_and_login(client, "alice", "secret123")
        bob_token   = register_and_login(client, "bob",   "secret456")

        alice_received = []
        bob_received   = []

        with client.stream("GET", "/stream", headers=auth(alice_token)) as alice_stream:
            with client.stream("GET", "/stream", headers=auth(bob_token)) as bob_stream:
                assert alice_stream.status_code == 200
                assert bob_stream.status_code == 200

                # alice → bob
                client.post(
                    "/messages",
                    json={"content": "ping bob", "recipient": "bob"},
                    headers=auth(alice_token),
                )

                for line in alice_stream.iter_lines():
                    if line.startswith("data:"):
                        alice_received.append(line)
                        break

                for line in bob_stream.iter_lines():
                    if line.startswith("data:"):
                        bob_received.append(line)
                        break

        assert len(alice_received) == 1
        assert len(bob_received) == 1
        assert "ping bob" in alice_received[0]
        assert "ping bob" in bob_received[0]
