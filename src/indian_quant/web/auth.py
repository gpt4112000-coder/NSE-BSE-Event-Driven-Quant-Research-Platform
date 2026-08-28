"""Authentication helpers: password hashing, session management."""

from __future__ import annotations

import bcrypt
from fastapi import Request
from starlette.exceptions import HTTPException


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_current_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def get_current_username(request: Request) -> str | None:
    return request.session.get("username")


def require_login(request: Request) -> int:
    uid = get_current_user_id(request)
    if uid is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return uid
