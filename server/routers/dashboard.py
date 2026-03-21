"""대시보드 API — PC 관리, 설정, 명령, 계정 분배"""
import datetime
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import create_token, require_admin, verify_password
from ..config import HEARTBEAT_TIMEOUT
from ..database import get_db
from ..models import CodeLog, Command, Computer, ComputerStatus

router = APIRouter(prefix="/api", tags=["dashboard"])


# ── 인증 ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, response: Response):
    user = verify_password(body.password)
    if not user:
        raise HTTPException(status_code=401, detail="비밀번호 틀림")
    token = create_token(user)
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=86400)
    print(f"[LOGIN] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} — {user} 로그인")
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}


# ── PC 관리 ────────────────────────────────────────────────────────────

def _check_online(status: ComputerStatus | None) -> bool:
    if not status or not status.last_heartbeat:
        return False
    elapsed = (datetime.datetime.utcnow() - status.last_heartbeat).total_seconds()
    return elapsed < HEARTBEAT_TIMEOUT


@router.get("/computers")
def list_computers(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computers = db.query(Computer).order_by(Computer.id).all()
    result = []
    for c in computers:
        status = db.query(ComputerStatus).filter(
            ComputerStatus.computer_id == c.id
        ).first()
        is_online = _check_online(status)
        if status and status.is_online != is_online:
            status.is_online = is_online
            db.commit()

        result.append({
            "id": c.id,
            "display_name": c.display_name,
            "config_version": c.config_version,
            "is_online": is_online,
            "monitoring_active": status.monitoring_active if status else False,
            "auto_input_active": status.auto_input_active if status else False,
            "last_code": status.last_code if status else "",
            "last_code_time": status.last_code_time.isoformat() if status and status.last_code_time else None,
            "success_count": status.success_count if status else 0,
            "fail_count": status.fail_count if status else 0,
            "app_version": status.app_version if status else "",
            "account_count": status.account_count if status else 0,
            "enabled_account_count": status.enabled_account_count if status else 0,
            "last_heartbeat": status.last_heartbeat.isoformat() if status and status.last_heartbeat else None,
        })
    return result


class CreateComputerRequest(BaseModel):
    id: str
    display_name: str = ""


@router.post("/computers")
def create_computer(
    body: CreateComputerRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    existing = db.query(Computer).filter(Computer.id == body.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 존재하는 PC ID")

    api_key = secrets.token_hex(16)
    computer = Computer(
        id=body.id,
        display_name=body.display_name or body.id,
        api_key=api_key,
    )
    db.add(computer)

    status = ComputerStatus(computer_id=body.id)
    db.add(status)
    db.commit()

    return {"id": computer.id, "api_key": api_key}


@router.delete("/computers/{computer_id}")
def delete_computer(
    computer_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=404, detail="PC 없음")

    db.query(ComputerStatus).filter(ComputerStatus.computer_id == computer_id).delete()
    db.query(Command).filter(Command.computer_id == computer_id).delete()
    db.query(CodeLog).filter(CodeLog.computer_id == computer_id).delete()
    db.delete(computer)
    db.commit()

    return {"ok": True}


# ── 설정 조회/수정 ────────────────────────────────────────────────────

@router.get("/computers/{computer_id}")
def get_computer(
    computer_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=404, detail="PC 없음")

    status = db.query(ComputerStatus).filter(
        ComputerStatus.computer_id == computer_id
    ).first()

    return {
        "id": computer.id,
        "display_name": computer.display_name,
        "api_key": computer.api_key,
        "config_version": computer.config_version,
        "config": json.loads(computer.config_json) if computer.config_json else {},
        "bonus_config": json.loads(computer.bonus_config_json) if computer.bonus_config_json else {},
        "is_online": _check_online(status),
        "status": {
            "monitoring_active": status.monitoring_active if status else False,
            "auto_input_active": status.auto_input_active if status else False,
            "last_code": status.last_code if status else "",
            "success_count": status.success_count if status else 0,
            "fail_count": status.fail_count if status else 0,
            "app_version": status.app_version if status else "",
            "account_count": status.account_count if status else 0,
            "enabled_account_count": status.enabled_account_count if status else 0,
        },
    }


class UpdateConfigRequest(BaseModel):
    config: dict | None = None
    bonus_config: dict | None = None
    display_name: str | None = None


@router.put("/computers/{computer_id}/config")
def update_config(
    computer_id: str,
    body: UpdateConfigRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=404, detail="PC 없음")

    if body.display_name is not None:
        computer.display_name = body.display_name
    if body.config is not None:
        computer.config_json = json.dumps(body.config, ensure_ascii=False)
        computer.config_version += 1
    if body.bonus_config is not None:
        computer.bonus_config_json = json.dumps(body.bonus_config, ensure_ascii=False)
        computer.config_version += 1

    computer.updated_at = datetime.datetime.utcnow()
    db.commit()

    return {"ok": True, "config_version": computer.config_version}


# ── 명령 전송 ──────────────────────────────────────────────────────────

class SendCommandRequest(BaseModel):
    command_type: str  # start_monitor, stop_monitor, submit_code
    payload: dict = {}


@router.post("/computers/{computer_id}/command")
def send_command(
    computer_id: str,
    body: SendCommandRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise HTTPException(status_code=404, detail="PC 없음")

    cmd = Command(
        computer_id=computer_id,
        command_type=body.command_type,
        payload=json.dumps(body.payload, ensure_ascii=False),
    )
    db.add(cmd)
    db.commit()

    return {"ok": True, "command_id": cmd.id}


# ── 계정 분배 ──────────────────────────────────────────────────────────

class DistributeAccountsRequest(BaseModel):
    accounts: list[dict]
    computer_ids: list[str]
    strategy: str = "even"  # even, sequential


@router.post("/computers/distribute-accounts")
def distribute_accounts(
    body: DistributeAccountsRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    computers = db.query(Computer).filter(Computer.id.in_(body.computer_ids)).all()
    if len(computers) != len(body.computer_ids):
        raise HTTPException(status_code=404, detail="일부 PC를 찾을 수 없음")

    n = len(computers)
    distributed = {c.id: [] for c in computers}

    if body.strategy == "even":
        for i, acct in enumerate(body.accounts):
            target_id = body.computer_ids[i % n]
            distributed[target_id].append(acct)
    else:  # sequential
        chunk_size = len(body.accounts) // n
        remainder = len(body.accounts) % n
        idx = 0
        for i, cid in enumerate(body.computer_ids):
            size = chunk_size + (1 if i < remainder else 0)
            distributed[cid] = body.accounts[idx:idx + size]
            idx += size

    for c in computers:
        config = json.loads(c.config_json) if c.config_json else {}
        config["accounts"] = distributed[c.id]
        config["account_index"] = 0
        c.config_json = json.dumps(config, ensure_ascii=False)
        c.config_version += 1

    db.commit()

    result = {cid: len(accts) for cid, accts in distributed.items()}
    return {"ok": True, "distribution": result}


# ── 코드 로그 조회 ────────────────────────────────────────────────────

@router.get("/computers/{computer_id}/logs")
def get_code_logs(
    computer_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    logs = db.query(CodeLog).filter(
        CodeLog.computer_id == computer_id
    ).order_by(CodeLog.detected_at.desc()).limit(limit).all()

    return [
        {
            "id": log.id,
            "code": log.code,
            "detected_at": log.detected_at.isoformat(),
            "total_accounts": log.total_accounts,
            "success_count": log.success_count,
            "fail_count": log.fail_count,
        }
        for log in logs
    ]


# ── 전체 코드 로그 (모든 PC) ──────────────────────────────────────────

@router.get("/logs")
def get_all_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    logs = db.query(CodeLog).order_by(CodeLog.detected_at.desc()).limit(limit).all()

    return [
        {
            "id": log.id,
            "computer_id": log.computer_id,
            "code": log.code,
            "detected_at": log.detected_at.isoformat(),
            "total_accounts": log.total_accounts,
            "success_count": log.success_count,
            "fail_count": log.fail_count,
        }
        for log in logs
    ]
