"""Accounts: email and password sign-up and sign-in. A session token is random and only its SHA-256 is stored; passwords are salted scrypt hashes."""
from __future__ import annotations
import hashlib, hmac, re, secrets, time, uuid
from datetime import datetime, timezone
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from .db import SessionRow, UserRow

SESSION_TTL_S = 7 * 24 * 3600
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,185}\.[^@\s]{2,}$")
_DUMMY_SALT = bytes(16)


class EmailTaken(Exception):
    pass


class BadLogin(Exception):
    pass


class SignupFull(Exception):
    pass


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def clean_email(email: str) -> str:
    e = email.strip().lower()
    if not EMAIL.match(e):
        raise ValueError("enter a valid email address")
    return e


def _public(u: UserRow) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "tenant": u.tenant, "role": u.role}


def create_user(sf, email: str, name: str, password: str, tenant: str, role: str, max_users: int) -> dict:
    e, salt = clean_email(email), secrets.token_bytes(16)
    with sf.begin() as s:
        if (s.scalar(select(func.count()).select_from(UserRow)) or 0) >= max_users:
            raise SignupFull()
        if s.scalar(select(UserRow.id).where(UserRow.email == e)):
            raise EmailTaken()
        u = UserRow(id="u_" + uuid.uuid4().hex[:12], email=e, name=name.strip(), pw_salt=salt.hex(), pw_hash=_scrypt(password, salt).hex(), tenant=tenant, role=role,
                    created=datetime.now(timezone.utc).isoformat())
        s.add(u)
        try:
            s.flush()
        except IntegrityError:                                     # two sign-ups with the same email at the same moment
            raise EmailTaken()
        return _public(u)


def start_session(sf, user: dict) -> str:
    token = "sp_" + secrets.token_urlsafe(32)
    with sf.begin() as s:
        s.execute(delete(SessionRow).where(SessionRow.expires < time.time()))      # expired sign-ins are cleared whenever a new one starts
        s.add(SessionRow(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user["id"], expires=time.time() + SESSION_TTL_S))
    return token


def login(sf, email: str, password: str) -> dict:
    try:
        e = clean_email(email)
    except ValueError:
        e = ""
    with sf() as s:
        u = s.scalar(select(UserRow).where(UserRow.email == e)) if e else None
    salt = bytes.fromhex(u.pw_salt) if u else _DUMMY_SALT
    ok = hmac.compare_digest(_scrypt(password, salt).hex(), u.pw_hash if u else "0" * 64)      # the hash runs even for an unknown email, so timing does not reveal which emails have accounts
    if not (u and ok):
        raise BadLogin()
    return _public(u)


def session_user(sf, token: str) -> dict | None:
    with sf() as s:
        row = s.get(SessionRow, hashlib.sha256(token.encode()).hexdigest())
        if row is None or row.expires < time.time():
            return None
        u = s.get(UserRow, row.user_id)
        return _public(u) if u else None


def end_session(sf, token: str) -> None:
    with sf.begin() as s:
        s.execute(delete(SessionRow).where(SessionRow.token_hash == hashlib.sha256(token.encode()).hexdigest()))
