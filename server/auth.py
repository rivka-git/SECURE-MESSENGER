"""
auth.py — Password hashing and JWT token logic.

╔══════════════════════════════════════════════╗
║  YOUR TASK: implement the five functions.    ║
╚══════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 1 — WHY WE HASH PASSWORDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Imagine every password in your database was stored as plain text.
  One database leak → every user's password is exposed, forever.

  bcrypt solves this by being a ONE-WAY function:
    hash("secret123") → "$2b$12$eImiTXuW..." (a fingerprint)
    There is no reverse. The original password is gone.

  When a user logs in, we don't un-hash. Instead we re-hash the
  typed password and compare the two fingerprints. If they match —
  the password was correct, without ever knowing the original.

  bcrypt is also INTENTIONALLY SLOW (has a "cost factor").
  Even if someone steals your DB, brute-forcing takes years.

  Use:
    import bcrypt
    hash  = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    match = bcrypt.checkpw(password.encode(), stored_hash.encode())

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 2 — WHY WE USE JWT TOKENS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  After a successful login, the server gives the client a JWT token.
  Think of it as a signed wristband at a concert:
    - It proves you paid (authenticated) without checking your ID again
    - It has an expiry date printed on it
    - The bouncer (server) can verify it's real by checking the signature
    - The server never needs to look up a database to validate it

  A JWT has three parts, separated by dots:
    header.payload.signature
    eyJhbGc...  .eyJzdWI...  .SflKxw...

  The payload contains the username and expiry time — readable but
  tamper-proof (changing anything breaks the signature).

  Use:
    from jose import jwt, JWTError
    token   = jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm="HS256")
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 3 — FASTAPI DEPENDENCY INJECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  require_auth() is a FastAPI "dependency". Instead of copy-pasting
  token validation into every route, you declare it once here and
  inject it into any route that needs it:

    @router.get("/messages")
    def get_messages(username: str = Depends(require_auth)):
        # username is already validated — if we got here, the token was valid
        ...

  FastAPI calls require_auth() automatically before your route runs.
  If the token is missing or invalid, it raises HTTP 401 and your
  route never executes.

  The HTTPBearer() helper extracts the token from the header:
    Authorization: Bearer eyJhbGc...
"""
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))


bearer_scheme = HTTPBearer()


# -------------------------------------------------
# 1. Hash password
# -------------------------------------------------
def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )
    return hashed.decode("utf-8")


# -------------------------------------------------
# 2. Verify password
# -------------------------------------------------
def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


# -------------------------------------------------
# 3. Create JWT token
# -------------------------------------------------
def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": username,
        "exp": expire
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# -------------------------------------------------
# 4. Decode / verify JWT token
# -------------------------------------------------
def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        return username

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# -------------------------------------------------
# 5. FastAPI dependency (require auth)
# -------------------------------------------------
def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> str:
    token = credentials.credentials
    username = decode_access_token(token)
    return username



