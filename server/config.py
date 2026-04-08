"""서버 설정 — 환경변수 기반"""
import os
import secrets

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
ADMIN_PASSWORD_2 = os.getenv("ADMIN_PASSWORD_2", "")
OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "")  # 코드 전송 전용 계정
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/data.db" if os.path.isdir("/data") else "sqlite:///./data.db")
HEARTBEAT_TIMEOUT = 30  # 초 — 이 시간 동안 heartbeat 없으면 오프라인
