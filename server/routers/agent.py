"""에이전트 API — heartbeat, config sync, command ack, code log"""
import datetime
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CodeLog, Command, Computer, ComputerStatus, Screenshot

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _get_computer(db: Session, api_key: str) -> Computer:
    computer = db.query(Computer).filter(Computer.api_key == api_key).first()
    if not computer:
        raise HTTPException(status_code=401, detail="유효하지 않은 API 키")
    return computer


# ── Heartbeat ──────────────────────────────────────────────────────────

class HeartbeatRequest(BaseModel):
    monitoring_active: bool = False
    auto_input_active: bool = False
    last_code: str = ""
    last_code_time: str | None = None
    success_count: int = 0
    fail_count: int = 0
    app_version: str = ""
    account_count: int = 0
    enabled_account_count: int = 0
    agent_version: str = ""
    recent_logs: list = []
    recent_errors: list = []


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatRequest,
    x_agent_key: str = Header(...),
    db: Session = Depends(get_db),
):
    computer = _get_computer(db, x_agent_key)
    now = datetime.datetime.utcnow()

    # 상태 업데이트 (upsert)
    status = db.query(ComputerStatus).filter(
        ComputerStatus.computer_id == computer.id
    ).first()
    if not status:
        status = ComputerStatus(computer_id=computer.id)
        db.add(status)

    status.is_online = True
    status.last_heartbeat = now
    status.monitoring_active = body.monitoring_active
    status.auto_input_active = body.auto_input_active
    status.last_code = body.last_code
    status.success_count = body.success_count
    status.fail_count = body.fail_count
    status.app_version = body.app_version
    status.account_count = body.account_count
    status.enabled_account_count = body.enabled_account_count
    status.agent_version = body.agent_version
    if body.recent_logs:
        status.recent_logs = json.dumps(body.recent_logs, ensure_ascii=False)
    if body.recent_errors is not None:
        status.recent_errors = json.dumps(body.recent_errors, ensure_ascii=False)

    if body.last_code_time:
        try:
            status.last_code_time = datetime.datetime.fromisoformat(body.last_code_time)
        except ValueError:
            pass

    # 대기 중인 명령 조회 (5분 이상 오래된 명령은 전부 자동 만료)
    cutoff = now - datetime.timedelta(minutes=5)
    old_cmds = db.query(Command).filter(
        Command.computer_id == computer.id,
        Command.status == "pending",
        Command.created_at < cutoff,
    ).all()
    for old in old_cmds:
        old.status = "expired"
        old.completed_at = now

    pending = db.query(Command).filter(
        Command.computer_id == computer.id,
        Command.status == "pending",
    ).order_by(Command.created_at).all()

    pending_commands = [
        {"id": cmd.id, "type": cmd.command_type, "payload": json.loads(cmd.payload)}
        for cmd in pending
    ]

    db.commit()

    return {
        "config_version": computer.config_version,
        "pending_commands": pending_commands,
    }


# ── Config 다운로드 ────────────────────────────────────────────────────

@router.get("/config")
def get_config(
    x_agent_key: str = Header(...),
    db: Session = Depends(get_db),
):
    computer = _get_computer(db, x_agent_key)
    return {
        "config_version": computer.config_version,
        "config": json.loads(computer.config_json) if computer.config_json else {},
        "bonus_config": json.loads(computer.bonus_config_json) if computer.bonus_config_json else {},
    }


# ── 명령 ACK ───────────────────────────────────────────────────────────

class CommandAckRequest(BaseModel):
    success: bool = True
    message: str = ""


@router.post("/command/{command_id}/ack")
def ack_command(
    command_id: int,
    body: CommandAckRequest,
    x_agent_key: str = Header(...),
    db: Session = Depends(get_db),
):
    computer = _get_computer(db, x_agent_key)
    cmd = db.query(Command).filter(
        Command.id == command_id,
        Command.computer_id == computer.id,
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="명령 없음")

    cmd.status = "completed" if body.success else "failed"
    cmd.completed_at = datetime.datetime.utcnow()
    db.commit()

    return {"ok": True}


# ── 스크린샷 업로드 ───────────────────────────────────────────────────

class ScreenshotUploadRequest(BaseModel):
    command_id: int
    image_base64: str


@router.post("/screenshot")
def upload_screenshot(
    body: ScreenshotUploadRequest,
    x_agent_key: str = Header(...),
    db: Session = Depends(get_db),
):
    computer = _get_computer(db, x_agent_key)

    # 기존 스크린샷 덮어쓰기 (upsert)
    existing = db.query(Screenshot).filter(
        Screenshot.computer_id == computer.id
    ).first()
    if existing:
        existing.image_data = body.image_base64
        existing.captured_at = datetime.datetime.utcnow()
    else:
        db.add(Screenshot(
            computer_id=computer.id,
            image_data=body.image_base64,
        ))

    # 명령 완료 처리
    cmd = db.query(Command).filter(Command.id == body.command_id).first()
    if cmd:
        cmd.status = "completed"
        cmd.completed_at = datetime.datetime.utcnow()

    db.commit()
    return {"ok": True}


# ── 코드 로그 ──────────────────────────────────────────────────────────

class CodeLogRequest(BaseModel):
    code: str
    total_accounts: int = 0
    success_count: int = 0
    fail_count: int = 0


@router.post("/code-log")
def post_code_log(
    body: CodeLogRequest,
    x_agent_key: str = Header(...),
    db: Session = Depends(get_db),
):
    computer = _get_computer(db, x_agent_key)
    log = CodeLog(
        computer_id=computer.id,
        code=body.code,
        total_accounts=body.total_accounts,
        success_count=body.success_count,
        fail_count=body.fail_count,
    )
    db.add(log)
    db.commit()

    return {"ok": True}
