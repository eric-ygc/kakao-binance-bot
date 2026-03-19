"""SSE — 실시간 대시보드 업데이트 스트림"""
import asyncio
import datetime
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..auth import require_admin
from ..config import HEARTBEAT_TIMEOUT
from ..database import get_db, SessionLocal
from ..models import ComputerStatus

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def event_stream(_=Depends(require_admin)):
    async def generate():
        while True:
            db = SessionLocal()
            try:
                statuses = db.query(ComputerStatus).all()
                now = datetime.datetime.utcnow()
                data = []
                for s in statuses:
                    is_online = (
                        s.last_heartbeat is not None
                        and (now - s.last_heartbeat).total_seconds() < HEARTBEAT_TIMEOUT
                    )
                    data.append({
                        "computer_id": s.computer_id,
                        "is_online": is_online,
                        "monitoring_active": s.monitoring_active,
                        "auto_input_active": s.auto_input_active,
                        "last_code": s.last_code,
                        "last_code_time": s.last_code_time.isoformat() if s.last_code_time else None,
                        "success_count": s.success_count,
                        "fail_count": s.fail_count,
                        "app_version": s.app_version,
                        "account_count": s.account_count,
                        "enabled_account_count": s.enabled_account_count,
                    })
                yield {"event": "status", "data": json.dumps(data, ensure_ascii=False)}
            finally:
                db.close()
            await asyncio.sleep(5)

    return EventSourceResponse(generate())
