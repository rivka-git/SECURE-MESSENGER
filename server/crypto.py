"""
crypto.py — AES-256-GCM encryption for messages stored in the database.

╔══════════════════════════════════════════════════════════════╗
║  THIS FILE IS COMPLETE — you do not need to change anything. ║
║  Read it, understand it, then use encrypt() and decrypt()    ║
║  in your routes.                                             ║
╚══════════════════════════════════════════════════════════════╝

HOW IT WORKS (the short version):
  The server has one secret key (256 bits, generated at startup).
  encrypt("hello") → scrambles the text into unreadable base64.
  decrypt(blob)    → unscrambles it back to "hello".
  Without the key, decryption is impossible.

WHY AES-GCM AND NOT JUST AES?
  GCM gives us two guarantees at once:
    1. Confidentiality — the content is hidden.
    2. Integrity      — if anyone tampers with the stored blob,
                        decryption raises an exception instead of
                        silently returning garbage.

WHY A FRESH NONCE EVERY TIME?
  Even if Alice sends "hello" ten times, each encrypted blob looks
  completely different. An attacker watching the database cannot
  detect repeated messages.

  The nonce is NOT secret — it is stored alongside the ciphertext.
  Its only job is to make each encryption unique.
"""

import os
import base64
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# 32 bytes = 256-bit key.
# Prefer a persistent key so messages remain decryptable across restarts.
# Load from environment variable `MESSENGER_KEY` (base64), else from
# ./messenger.key (base64). If neither exists, generate and save a key.
_KEY_PATH = Path(__file__).parent.parent / "messenger.key"
_KEY_B64 = os.getenv("MESSENGER_KEY")
if _KEY_B64:
  try:
    _KEY = base64.b64decode(_KEY_B64)
  except Exception:
    # fallback to random key if env var malformed
    _KEY = os.urandom(32)
elif _KEY_PATH.exists():
  try:
    _KEY = base64.b64decode(_KEY_PATH.read_text())
  except Exception:
    _KEY = os.urandom(32)
else:
  _KEY = os.urandom(32)
  try:
    _KEY_PATH.write_text(base64.b64encode(_KEY).decode())
  except Exception:
    # ignore write failures (e.g., permissions)
    pass


def encrypt(plaintext: str) -> str:
    """
    Encrypt a string. Returns a base64 blob safe to store in the database.

    Blob layout (concatenated, then base64-encoded):
        [ nonce: 12 bytes ][ ciphertext + auth-tag: variable ]
    """
    aesgcm = AESGCM(_KEY)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(blob: str) -> str:
    """
    Decrypt a blob produced by encrypt(). Raises an exception if tampered with.
    """
    raw = base64.b64decode(blob.encode())
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
