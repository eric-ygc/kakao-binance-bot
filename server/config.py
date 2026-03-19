"""서버 설정 — 환경변수 기반"""
import os
import secrets

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
HEARTBEAT_TIMEOUT = 30  # 초 — 이 시간 동안 heartbeat 없으면 오프라인
