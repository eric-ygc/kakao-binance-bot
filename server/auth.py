"""인증 — 비밀번호 + JWT (admin / operator 역할)"""
import datetime

import jwt
from fastapi import Cookie, Depends, HTTPException

from .config import ADMIN_PASSWORD, ADMIN_PASSWORD_2, OPERATOR_PASSWORD, JWT_SECRET

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def verify_password(password: str) -> str | None:
    """비밀번호 확인 → 성공 시 역할 반환 (admin1/admin2/operator), 실패 시 None."""
    import logging
    logger = logging.getLogger("auth")
    if password == ADMIN_PASSWORD:
        logger.info("로그인 성공: admin1")
        return "admin1"
    if ADMIN_PASSWORD_2 and password == ADMIN_PASSWORD_2:
        logger.info("로그인 성공: admin2")
        return "admin2"
    if OPERATOR_PASSWORD and password == OPERATOR_PASSWORD:
        logger.info("로그인 성공: operator")
        return "operator"
    logger.warning("로그인 실패")
    return None


def create_token(user: str = "admin") -> str:
    payload = {
        "sub": user,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="로그인 필요")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰 만료")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰")


def require_admin(token: str = Cookie(None)):
    """관리자 전용 (admin1, admin2)"""
    payload = _decode_token(token)
    if payload.get("sub") == "operator":
        raise HTTPException(status_code=403, detail="관리자 권한 필요")
    return payload


def require_login(token: str = Cookie(None)):
    """로그인만 확인 (admin + operator 모두 허용)"""
    return _decode_token(token)


def get_role(token: str = Cookie(None)) -> str:
    """현재 사용자 역할 반환"""
    payload = _decode_token(token)
    return payload.get("sub", "admin1")
