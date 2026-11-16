"""Role-based login: username + password, JWT access tokens and rotating refresh tokens.

Roles
    admin     everything, plus user management (/api/users)
    operator  view + every import / upload / LTP change
    viewer    view only (GET requests)

Tokens
    Access token   JWT (HS256), ACCESS_TOKEN_MINUTES (default 15) long. The frontend keeps it
                   in memory and sends it on every request: "Authorization: Bearer <token>".
    Refresh token  JWT, REFRESH_TOKEN_DAYS (default 7) long, in an httpOnly SameSite=Strict
                   cookie limited to /api/auth, so page scripts can never read it. Every use
                   rotates it (the old one is revoked). Each one is recorded in
                   ``refresh_tokens`` so it can be revoked. Reusing a rotated token (a sign of
                   theft) revokes that whole login session.

Every access token carries the user's ``token_version``. Changing a user's password,
role or active flag bumps the version, so their existing tokens stop working at once.
The user is read from the database on each request, so a disabled user is locked out
immediately.

Every /api route needs a valid access token except PUBLIC_PATHS. The guard is attached
to the whole app (main.py), so new routes are protected without extra code.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config import (ACCESS_TOKEN_MINUTES, COOKIE_SECURE, JWT_ALGORITHM, JWT_SECRET, MONGODB_DATABASE,
                     MONGODB_URI, REFRESH_TOKEN_DAYS)

if len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET is missing or too short (min 32 characters). Set it in backend/.env, e.g. "
        "python -c \"import secrets;print(secrets.token_urlsafe(48))\"")

ROLES = ("admin", "operator", "viewer")
WRITE_ROLES = {"admin", "operator"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/refresh", "/api/auth/logout"}

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"
REUSE_GRACE_SECONDS = 10       # two tabs refreshing at the same moment is not treated as theft
PBKDF2_ITERATIONS = 600_000
USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,32}$"
MIN_PASSWORD, MAX_PASSWORD = 8, 128
LOGIN_MAX_FAILURES = 5         # per username + IP ...
LOGIN_WINDOW_SECONDS = 15 * 60  # ... within this window, then locked for the rest of it


# --------------------------------------------------------------------------
# Passwords (PBKDF2-SHA256, standard library)
# --------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
        return hmac.compare_digest(candidate, _unb64(digest))
    except (ValueError, TypeError):
        return False


_dummy_hash = None


def _dummy():
    """A real hash to check against when the user does not exist (same timing as a real check)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


def check_new_password(password: str, username: str):
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise HTTPException(400, f"Password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
    if password.lower() == username.lower():
        raise HTTPException(400, "Password must not be the username.")


# --------------------------------------------------------------------------
# Storage: users and refresh tokens
# --------------------------------------------------------------------------

_client = None
_ready = False
_lock = threading.Lock()


def get_db():
    global _client, _ready
    with _lock:
        if _client is None:
            _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2500)
        db = _client[MONGODB_DATABASE]
        if not _ready:
            db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0, name="ttl_expires")
            db.refresh_tokens.create_index("username", name="ix_username")
            db.refresh_tokens.create_index("family", name="ix_family")
            _ready = True
    return db


def _now():
    """Naive UTC, as MongoDB returns dates."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def public_user(user):
    return {"username": user["username"], "role": user["role"], "active": user.get("active", True),
            "created_at": user.get("created_at"), "last_login_at": user.get("last_login_at")}


def find_user(db, username):
    return db.users.find_one({"_id": (username or "").strip().lower()})


def create_user(db, username, password, role, created_by=None):
    username = username.strip()
    if role not in ROLES:
        raise HTTPException(400, f"Role must be one of: {', '.join(ROLES)}.")
    check_new_password(password, username)
    now = _now()
    user = {"_id": username.lower(), "username": username, "password_hash": hash_password(password),
            "role": role, "active": True, "token_version": 0, "created_at": now, "updated_at": now,
            "created_by": created_by, "last_login_at": None}
    try:
        db.users.insert_one(user)
    except DuplicateKeyError as exc:
        raise HTTPException(409, f"User '{username}' already exists.") from exc
    return user


def end_sessions(db, username, reason):
    """Revoke every refresh token of a user (their access tokens die with the version bump)."""
    db.refresh_tokens.update_many({"username": username, "revoked_at": None},
                                  {"$set": {"revoked_at": _now(), "revoked_reason": reason}})


def update_user(db, username, *, password=None, role=None, active=None):
    """Change password / role / active; bumps token_version so old tokens stop working."""
    changes = {"updated_at": _now()}
    if password is not None:
        check_new_password(password, username)
        changes["password_hash"] = hash_password(password)
    if role is not None:
        if role not in ROLES:
            raise HTTPException(400, f"Role must be one of: {', '.join(ROLES)}.")
        changes["role"] = role
    if active is not None:
        changes["active"] = bool(active)
    user = db.users.find_one_and_update({"_id": username.lower()}, {"$set": changes, "$inc": {"token_version": 1}},
                                        return_document=True)
    if user is None:
        raise HTTPException(404, f"User '{username}' not found.")
    end_sessions(db, user["_id"], "user changed")
    return user


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

def _unauthorized(detail):
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _encode(payload):
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token, kind):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                             options={"require": ["exp", "iat", "sub", "type"]})
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Session expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token.") from exc
    if payload.get("type") != kind:
        raise _unauthorized("Invalid token.")
    return payload


def access_token(user):
    now = datetime.now(timezone.utc)
    return _encode({"sub": user["_id"], "role": user["role"], "ver": user.get("token_version", 0),
                    "type": "access", "iat": now, "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES)})


def _refresh_token(db, user, family, request):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=REFRESH_TOKEN_DAYS)
    jti = uuid.uuid4().hex
    db.refresh_tokens.insert_one({
        "_id": jti, "username": user["_id"], "family": family, "ver": user.get("token_version", 0),
        "created_at": now.replace(tzinfo=None), "expires_at": expires.replace(tzinfo=None),
        "revoked_at": None, "revoked_reason": None,
        "ip": request.client.host if request.client else None,
        "user_agent": (request.headers.get("user-agent") or "")[:200],
    })
    token = _encode({"sub": user["_id"], "type": "refresh", "jti": jti, "fam": family,
                     "ver": user.get("token_version", 0), "iat": now, "exp": expires})
    return token


def _session(response, db, user, request, family=None):
    """Body with a new access token; sets a new refresh token cookie."""
    token = _refresh_token(db, user, family or uuid.uuid4().hex, request)
    response.set_cookie(REFRESH_COOKIE, token, max_age=REFRESH_TOKEN_DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite="strict", path=COOKIE_PATH)
    return {"access_token": access_token(user), "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60, "user": public_user(user)}


def _signed_out(detail):
    """401 that also removes the refresh cookie."""
    response = JSONResponse({"detail": detail}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, secure=COOKIE_SECURE, httponly=True, samesite="strict")
    return response


# --------------------------------------------------------------------------
# Login throttling (in memory, per username + IP)
# --------------------------------------------------------------------------

_failures: dict[tuple, list[float]] = {}
_failures_lock = threading.Lock()


def _recent_failures(key):
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    with _failures_lock:
        times = [t for t in _failures.get(key, []) if t > cutoff]
        _failures[key] = times
        return times


def _record_failure(key):
    with _failures_lock:
        _failures.setdefault(key, []).append(time.monotonic())


def _clear_failures(key):
    with _failures_lock:
        _failures.pop(key, None)


# --------------------------------------------------------------------------
# Guard (attached to the whole app) and role checks
# --------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def require_login(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Every /api request: valid access token, active user, and a role allowed for the method."""
    path = request.url.path
    if path in PUBLIC_PATHS or request.method == "OPTIONS":
        return None
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    payload = decode_token(credentials.credentials, "access")
    try:
        user = find_user(get_db(), payload["sub"])
    except PyMongoError as exc:
        raise HTTPException(503, f"Unable to check the session: {exc}") from exc
    if not user or not user.get("active", True) or user.get("token_version", 0) != payload.get("ver"):
        raise _unauthorized("Your session has ended. Sign in again.")
    if (request.method not in SAFE_METHODS and user["role"] not in WRITE_ROLES
            and not path.startswith("/api/auth/")):
        raise HTTPException(403, f"Your role ({user['role']}) can only view data.")
    request.state.user = user
    return user


def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise _unauthorized("Sign in to continue.")
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only an admin can manage users.")
    return user


# --------------------------------------------------------------------------
# /api/auth
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    """Username + password -> access token (body) and refresh token (httpOnly cookie)."""
    key = (body.username.strip().lower(), request.client.host if request.client else "")
    if len(_recent_failures(key)) >= LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many failed sign-ins. Try again in 15 minutes.",
                            headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)})
    db = get_db()
    user = find_user(db, body.username)
    valid = verify_password(body.password, user["password_hash"] if user else _dummy())
    if not user or not valid:
        _record_failure(key)
        raise _unauthorized("Wrong username or password.")
    if not user.get("active", True):
        raise _unauthorized("This account is disabled. Ask an admin.")
    _clear_failures(key)
    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": _now()}})
    return _session(response, db, user, request)


@router.post("/refresh")
def refresh(request: Request, response: Response):
    """Refresh token cookie -> new access token; the refresh token is rotated."""
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return _signed_out("Sign in to continue.")
    try:
        payload = decode_token(token, "refresh")
    except HTTPException as exc:
        return _signed_out(exc.detail)
    db = get_db()
    now = _now()
    record = db.refresh_tokens.find_one_and_update(
        {"_id": payload.get("jti"), "revoked_at": None, "expires_at": {"$gt": now}},
        {"$set": {"revoked_at": now, "revoked_reason": "rotated"}})
    if record is None:
        old = db.refresh_tokens.find_one({"_id": payload.get("jti")})
        rotated = old and old.get("revoked_reason") == "rotated"
        if rotated and (now - old["revoked_at"]).total_seconds() <= REUSE_GRACE_SECONDS:
            record = old  # another tab refreshed a moment ago
        else:
            if rotated:  # an already-used token came back: end that whole login session
                db.refresh_tokens.update_many({"family": old["family"], "revoked_at": None},
                                              {"$set": {"revoked_at": now, "revoked_reason": "reuse detected"}})
            return _signed_out("Your session has ended. Sign in again.")
    user = find_user(db, record["username"])
    if not user or not user.get("active", True) or user.get("token_version", 0) != payload.get("ver"):
        return _signed_out("Your session has ended. Sign in again.")
    return _session(response, db, user, request, family=record["family"])


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = decode_token(token, "refresh")
            get_db().refresh_tokens.update_one({"_id": payload.get("jti"), "revoked_at": None},
                                               {"$set": {"revoked_at": _now(), "revoked_reason": "logout"}})
        except HTTPException:
            pass
    response = JSONResponse({"ok": True})
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, secure=COOKIE_SECURE, httponly=True, samesite="strict")
    return response


@router.get("/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.post("/change-password")
def change_password(body: PasswordChange, request: Request, response: Response, user=Depends(current_user)):
    """Own password. Signs out every other session; this browser gets new tokens."""
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "Current password is wrong.")
    db = get_db()
    updated = update_user(db, user["_id"], password=body.new_password)
    return _session(response, db, updated, request)


# --------------------------------------------------------------------------
# /api/users (admin only)
# --------------------------------------------------------------------------

users_router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


class NewUser(BaseModel):
    username: str = Field(..., pattern=USERNAME_PATTERN)
    password: str = Field(..., min_length=1, max_length=256)
    role: str = Field("viewer")


class UserChange(BaseModel):
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(None, min_length=1, max_length=256)


@users_router.get("")
def list_users():
    return [public_user(u) for u in get_db().users.find().sort("_id", 1)]


@users_router.post("", status_code=201)
def add_user(body: NewUser, admin=Depends(require_admin)):
    return public_user(create_user(get_db(), body.username, body.password, body.role, created_by=admin["_id"]))


@users_router.patch("/{username}")
def change_user(username: str, body: UserChange, admin=Depends(require_admin)):
    db = get_db()
    target = find_user(db, username)
    if target is None:
        raise HTTPException(404, f"User '{username}' not found.")
    if target["_id"] == admin["_id"] and body.active is False:
        raise HTTPException(400, "You cannot disable your own account.")
    loses_admin = target["role"] == "admin" and target.get("active", True) and (
        (body.role is not None and body.role != "admin") or body.active is False)
    if loses_admin and db.users.count_documents({"role": "admin", "active": True, "_id": {"$ne": target["_id"]}}) == 0:
        raise HTTPException(400, "There must be at least one active admin.")
    if body.role is None and body.active is None and body.password is None:
        return public_user(target)
    return public_user(update_user(db, target["_id"], password=body.password, role=body.role, active=body.active))
