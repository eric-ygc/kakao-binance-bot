"""인증 — 비밀번호 + JWT"""
import datetime

import jwt
from fastapi import Cookie, Depends, HTTPException

from .config import ADMIN_PASSWORD, ADMIN_PASSWORD_2, JWT_SECRET

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def verify_password(password: str) -> str | None:
    """비밀번호 확인 → 성공 시 사용자 라벨 반환, 실패 시 None."""
    if password == ADMIN_PASSWORD:
        return "admin1"
    if ADMIN_PASSWORD_2 and password == ADMIN_PASSWORD_2:
        return "admin2"
    return None


def create_token(user: str = "admin") -> str:
    payload = {
        "sub": user,
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
