"""픽보조 에이전트 — 서버와 로컬 앱 사이 중계"""
import base64
import io
import json
import logging
import sys
import time
from pathlib import Path

import requests

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

AGENT_CONFIG_PATH = BASE_DIR / "agent_config.json"
STATUS_PATH = BASE_DIR / "status.json"
COMMANDS_PATH = BASE_DIR / "commands.json"
CONFIG_PATH = BASE_DIR / "config.json"
BONUS_CONFIG_PATH = BASE_DIR / "bonus_config.json"

HEARTBEAT_INTERVAL = 5  # 초

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("agent")


def load_agent_config() -> dict:
    if not AGENT_CONFIG_PATH.exists():
        logger.error(f"에이전트 설정 파일 없음: {AGENT_CONFIG_PATH}")
        logger.error("agent_config.json 파일을 생성해주세요.")
        logger.error('예: {"server_url": "https://...", "api_key": "..."}')
        sys.exit(1)
    with open(AGENT_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def read_local_status() -> dict:
    """픽보조 앱이 기록한 status.json 읽기"""
    if not STATUS_PATH.exists():
        return {}
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_config(config: dict, path: Path):
    """서버에서 받은 설정을 로컬 파일에 저장"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"설정 파일 업데이트: {path.name}")
    except Exception as e:
        logger.error(f"설정 파일 저장 실패: {e}")


def write_commands(commands: list):
    """명령을 commands.json에 기록 (픽보조 앱이 읽고 실행)"""
    try:
        existing = []
        if COMMANDS_PATH.exists():
            with open(COMMANDS_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        existing.extend(commands)
        with open(COMMANDS_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"명령 파일 저장 실패: {e}")


class PickAgent:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.local_config_version = 0
        self.session = requests.Session()
        self.session.headers["X-Agent-Key"] = api_key

    def run(self):
        logger.info(f"에이전트 시작 — 서버: {self.server_url}")
        while True:
            try:
                self._tick()
            except requests.ConnectionError:
                logger.warning("서버 연결 실패 — 5초 후 재시도")
            except Exception as e:
                logger.error(f"에이전트 오류: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

    def _tick(self):
        # 1. 로컬 상태 읽기
        status = read_local_status()

        # 2. Heartbeat 전송
        resp = self.session.post(
            f"{self.server_url}/api/agent/heartbeat",
            json={
                "monitoring_active": status.get("monitoring_active", False),
                "auto_input_active": status.get("auto_input_active", False),
                "last_code": status.get("last_code", ""),
                "last_code_time": status.get("last_code_time"),
                "success_count": status.get("success_count", 0),
                "fail_count": status.get("fail_count", 0),
                "app_version": status.get("app_version", ""),
                "account_count": status.get("account_count", 0),
                "enabled_account_count": status.get("enabled_account_count", 0),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # 3. 설정 동기화
        server_version = data.get("config_version", 0)
        if server_version > self.local_config_version:
            self._sync_config()
            self.local_config_version = server_version

        # 4. 대기 중인 명령 처리
        pending = data.get("pending_commands", [])
        if pending:
            self._handle_commands(pending)

    def _sync_config(self):
        resp = self.session.get(
            f"{self.server_url}/api/agent/config",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("config"):
            write_config(data["config"], CONFIG_PATH)

        if data.get("bonus_config"):
            write_config(data["bonus_config"], BONUS_CONFIG_PATH)

        self.local_config_version = data.get("config_version", 0)
        logger.info(f"설정 동기화 완료 (version={self.local_config_version})")

    def _handle_commands(self, commands: list):
        local_cmds = []
        for cmd in commands:
            cmd_type = cmd.get("type", "")
            cmd_id = cmd.get("id")
            payload = cmd.get("payload", {})

            logger.info(f"명령 수신: {cmd_type} (id={cmd_id})")

            # 스크린샷 명령은 에이전트가 직접 처리
            if cmd_type == "screenshot":
                self._capture_and_upload(cmd_id)
                continue

            # 나머지 명령은 commands.json에 기록하여 픽보조 앱이 처리
            local_cmds.append({
                "id": cmd_id,
                "type": cmd_type,
                "payload": payload,
            })

            # ACK 전송
            try:
                self.session.post(
                    f"{self.server_url}/api/agent/command/{cmd_id}/ack",
                    json={"success": True},
                    timeout=10,
                )
            except Exception as e:
                logger.error(f"ACK 전송 실패: {e}")

        if local_cmds:
            write_commands(local_cmds)

    def _capture_and_upload(self, command_id: int):
        """화면 캡처 후 서버에 업로드"""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")

            self.session.post(
                f"{self.server_url}/api/agent/screenshot",
                json={"command_id": command_id, "image_base64": encoded},
                timeout=30,
            )
            logger.info(f"스크린샷 업로드 완료 (id={command_id})")
        except Exception as e:
            logger.error(f"스크린샷 캡처/업로드 실패: {e}")
            try:
                self.session.post(
                    f"{self.server_url}/api/agent/command/{command_id}/ack",
                    json={"success": False, "message": str(e)},
                    timeout=10,
                )
            except Exception:
                pass

    def report_code(self, code: str, total: int, success: int, fail: int):
        """코드 제출 결과 보고"""
        try:
            self.session.post(
                f"{self.server_url}/api/agent/code-log",
                json={
                    "code": code,
                    "total_accounts": total,
                    "success_count": success,
                    "fail_count": fail,
                },
                timeout=10,
            )
        except Exception as e:
            logger.error(f"코드 로그 전송 실패: {e}")


def main():
    cfg = load_agent_config()
    agent = PickAgent(
        server_url=cfg["server_url"],
        api_key=cfg["api_key"],
    )
    agent.run()


if __name__ == "__main__":
    main()
