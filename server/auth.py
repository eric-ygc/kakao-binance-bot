"""인증 — 비밀번호 + JWT"""
import datetime

import jwt
from fastapi import Cookie, Depends, HTTPException

from .config import ADMIN_PASSWORD, JWT_SECRET

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def verify_password(password: str) -> bool:
    return password == ADMIN_PASSWORD


def create_token() -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def require_admin(token: str = Cookie(None)):
    if not token:
        raise HTTPException(status_code=401, detail="로그인 필요")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰 만료")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
