"""
시스템모니터용 보안 에이전트
- agent_config.json의 API 키를 암호화된 상태로 저장/읽기
- 픽보조 에이전트와 동일한 기능
"""
AGENT_VERSION = "1.1.5"  # 에이전트 버전

import base64
import io
import json
import logging
import sys
import time
from pathlib import Path

import requests

# ── 경로 설정 ──
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# ── 암호화 키 ──
_KEY = b"PickBozo2026SystemMonitor"

def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def encrypt_text(plain: str) -> str:
    encrypted = _xor_bytes(plain.encode("utf-8"), _KEY)
    return base64.b64encode(encrypted).decode("ascii")

def decrypt_text(encoded: str) -> str:
    encrypted = base64.b64decode(encoded)
    return _xor_bytes(encrypted, _KEY).decode("utf-8")

# ── 파일 경로 ──
AGENT_CONFIG_PATH = BASE_DIR / "agent_config.json"
STATUS_PATH = BASE_DIR / "status.json"
COMMANDS_PATH = BASE_DIR / "commands.json"
CONFIG_PATH = BASE_DIR / "config.json"
BONUS_CONFIG_PATH = BASE_DIR / "bonus_config.json"

HEARTBEAT_INTERVAL = 5  # 초

# ── 로그 설정 ──
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
    """agent_config.json 로드 + API 키 복호화"""
    if not AGENT_CONFIG_PATH.exists():
        logger.error(f"에이전트 설정 파일 없음: {AGENT_CONFIG_PATH}")
        sys.exit(1)
    with open(AGENT_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    # API 키 복호화
    if "api_key" in config and config["api_key"].startswith("ENC:"):
        config["api_key"] = decrypt_text(config["api_key"][4:])
    return config


def auto_encrypt_config():
    """평문 API 키가 있으면 자동으로 암호화"""
    if not AGENT_CONFIG_PATH.exists():
        return
    with open(AGENT_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    if "api_key" in config and config["api_key"] and not config["api_key"].startswith("ENC:"):
        config["api_key"] = "ENC:" + encrypt_text(config["api_key"])
        with open(AGENT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("API 키 암호화 완료")


def read_local_status() -> dict:
    """앱이 기록한 status.json 읽기"""
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
    """명령을 commands.json에 기록"""
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
                # .pending 파일 감지 → 즉시 적용 + 재시작
                if check_and_apply_pending():
                    return  # 새 프로세스 시작됨, 현재 종료
                self._tick()
            except requests.ConnectionError:
                logger.warning("서버 연결 실패 — 5초 후 재시도")
            except Exception as e:
                logger.error(f"에이전트 오류: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

    def _tick(self):
        status = read_local_status()
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
                "agent_version": AGENT_VERSION,
                "account_count": status.get("account_count", 0),
                "enabled_account_count": status.get("enabled_account_count", 0),
                "recent_logs": status.get("recent_logs", []),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        server_version = data.get("config_version", 0)
        if server_version > self.local_config_version:
            self._sync_config()
            self.local_config_version = server_version

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

            # 에이전트가 직접 처리하는 명령
            if cmd_type == "screenshot":
                self._capture_and_upload(cmd_id)
                continue
            if cmd_type == "update_exe":
                self._update_exe(cmd_id, payload)
                continue
            if cmd_type == "remote_click":
                self._remote_click(cmd_id, payload)
                continue
            if cmd_type == "remote_key":
                self._remote_key(cmd_id, payload)
                continue
            if cmd_type == "run_command":
                self._run_command(cmd_id, payload)
                continue
            if cmd_type == "update_agent":
                self._update_agent(cmd_id, payload)
                continue

            # 나머지 → commands.json
            local_cmds.append({"id": cmd_id, "type": cmd_type, "payload": payload})
            self._ack(cmd_id, True)

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
            self._ack(command_id, False, str(e))

    def _remote_click(self, command_id: int, payload: dict):
        """원격 마우스 클릭"""
        try:
            import pyautogui
            x = payload.get("x", 0)
            y = payload.get("y", 0)
            click_type = payload.get("click_type", "left")
            if click_type == "double":
                pyautogui.doubleClick(x, y)
            elif click_type == "right":
                pyautogui.rightClick(x, y)
            else:
                pyautogui.click(x, y)
            logger.info(f"원격 클릭: ({x}, {y}) {click_type}")
            self._ack(command_id, True)
        except Exception as e:
            logger.error(f"원격 클릭 실패: {e}")
            self._ack(command_id, False, str(e))

    def _remote_key(self, command_id: int, payload: dict):
        """원격 키보드 입력"""
        try:
            import pyautogui
            text = payload.get("text", "")
            key = payload.get("key", "")
            if text:
                pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
            if key:
                pyautogui.press(key)
            logger.info(f"원격 키 입력: text='{text}' key='{key}'")
            self._ack(command_id, True)
        except Exception as e:
            logger.error(f"원격 키 입력 실패: {e}")
            self._ack(command_id, False, str(e))

    def _run_command(self, command_id: int, payload: dict):
        """원격 셸 명령 실행"""
        import subprocess
        cmd = payload.get("command", "")
        if not cmd:
            self._ack(command_id, False, "command 없음")
            return
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            output = (result.stdout + result.stderr).strip()
            logger.info(f"원격 명령 실행: {cmd} → {output[:200]}")
            self._ack(command_id, True, output[:500])
        except subprocess.TimeoutExpired:
            logger.error(f"원격 명령 타임아웃: {cmd}")
            self._ack(command_id, False, "타임아웃 (30초)")
        except Exception as e:
            logger.error(f"원격 명령 실패: {e}")
            self._ack(command_id, False, str(e))

    def _update_agent(self, command_id: int, payload: dict):
        """에이전트 자체 업데이트 (다운로드만, 다음 시작 시 자동 교체)"""
        download_url = payload.get("download_url", "")
        if not download_url:
            self._ack(command_id, False, "download_url 없음")
            return
        try:
            exe_path = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__).resolve()
            pending_path = exe_path.with_suffix(exe_path.suffix + ".pending")

            # 1. 다운로드
            logger.info(f"에이전트 업데이트 다운로드: {download_url}")
            resp = requests.get(download_url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(pending_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"다운로드 완료: {pending_path.stat().st_size} bytes")

            # 2. 다운로드 검증
            if pending_path.stat().st_size < 1000:
                pending_path.unlink()
                raise RuntimeError(f"다운로드 파일 크기 비정상")

            # 3. ACK — 다음 재시작 시 적용됨
            self._ack(command_id, True, "에이전트 업데이트 다운로드 완료 — 다음 재시작 시 적용")
            logger.info("에이전트 업데이트 대기 중 (.pending) — 앱 업데이트 또는 재시작 시 자동 적용")

        except Exception as e:
            logger.error(f"에이전트 업데이트 실패: {e}")
            self._ack(command_id, False, str(e))

    def _update_exe(self, command_id: int, payload: dict):
        """exe 다운로드 → 교체 → 앱 재시작"""
        import subprocess
        import shutil

        download_url = payload.get("download_url", "")
        version = payload.get("version", "")
        exe_name = payload.get("exe_name", "")
        if not download_url:
            self._ack(command_id, False, "download_url 없음")
            return
        if not exe_name:
            cfg = load_agent_config()
            exe_name = cfg.get("exe_name", "시스템모니터.exe")

        # 에이전트 자신을 update_exe로 업데이트 시도 시 거부 (update_agent 사용)
        if getattr(sys, "frozen", False):
            my_name = Path(sys.executable).name
            if exe_name.lower() == my_name.lower():
                logger.warning(f"update_exe로 에이전트 자신 업데이트 거부: {exe_name} → update_agent 사용하세요")
                self._ack(command_id, False, "에이전트는 update_agent로 업데이트하세요")
                return

        exe_path = BASE_DIR / exe_name
        backup_path = BASE_DIR / f"{exe_name}.backup"
        temp_path = BASE_DIR / f"{exe_name}.new"

        try:
            logger.info(f"업데이트 다운로드 시작: {download_url}")
            resp = requests.get(download_url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"다운로드 완료: {temp_path} ({temp_path.stat().st_size} bytes)")

            # 관련 프로세스 모두 종료 (한글/영문 이름 모두)
            kill_names = {exe_name}
            # 픽보조 관련 프로세스명 추가
            for name in ["픽보조.exe", "픽보조_Selenium.exe", "PicAssist_API.exe",
                         "PicAssist_Selenium.exe", "시스템모니터.exe", "SystemMonitor.exe"]:
                kill_names.add(name)
            logger.info(f"앱 종료 시도: {exe_name} (관련 프로세스 전체)")
            for attempt in range(3):
                for kname in kill_names:
                    try:
                        subprocess.run(["taskkill", "/f", "/im", kname],
                                     capture_output=True, timeout=10)
                    except Exception:
                        pass
                time.sleep(5)
                try:
                    result = subprocess.run(["tasklist", "/fi", f"imagename eq {exe_name}"],
                                          capture_output=True, text=True, timeout=10)
                    if exe_name.lower() not in result.stdout.lower():
                        logger.info("앱 종료 확인")
                        break
                except Exception:
                    pass

            # 파일 잠금 해제 대기
            time.sleep(3)

            if exe_path.exists():
                shutil.copy2(exe_path, backup_path)
                logger.info(f"백업 완료: {backup_path}")

            # 파일 교체 (잠금 시 최대 3회 재시도)
            for retry in range(3):
                try:
                    shutil.move(str(temp_path), str(exe_path))
                    logger.info(f"교체 완료: {exe_path}")
                    break
                except PermissionError:
                    logger.warning(f"파일 잠금 — 재시도 {retry+1}/3")
                    time.sleep(5)
            else:
                raise RuntimeError(f"파일 교체 실패: {exe_name} 잠금 해제 안 됨")

            try:
                with open(COMMANDS_PATH, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass

            subprocess.Popen([str(exe_path)], cwd=str(BASE_DIR))
            logger.info(f"앱 재시작: {exe_path}")
            self._ack(command_id, True, f"업데이트 완료: v{version}")

        except Exception as e:
            logger.error(f"업데이트 실패: {e}")
            if backup_path.exists() and not exe_path.exists():
                shutil.move(str(backup_path), str(exe_path))
            if temp_path.exists():
                temp_path.unlink()
            self._ack(command_id, False, str(e))

    def _ack(self, command_id: int, success: bool, message: str = ""):
        try:
            self.session.post(
                f"{self.server_url}/api/agent/command/{command_id}/ack",
                json={"success": success, "message": message},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"ACK 전송 실패: {e}")


def check_and_apply_pending() -> bool:
    """
    .pending 파일이 있으면 자동 교체 + 재시작.
    Windows에서 실행 중인 exe는 삭제/덮어쓰기 불가 → 이름 변경 후 교체.
    반환: True면 새 프로세스 시작됨 (호출자는 종료해야 함)
    """
    if not getattr(sys, "frozen", False):
        return False
    import shutil
    import subprocess
    exe_path = Path(sys.executable)
    pending_path = exe_path.with_suffix(exe_path.suffix + ".pending")
    if not pending_path.exists():
        return False
    try:
        old_path = exe_path.with_suffix(exe_path.suffix + ".old")
        # 이전 .old 파일 삭제
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass
        # 실행 중인 exe 이름 변경 (Windows에서 가능)
        exe_path.rename(old_path)
        # .pending → 원래 이름으로 이동
        shutil.move(str(pending_path), str(exe_path))
        logger.info(f"에이전트 업데이트 적용: {exe_path.name}")
        # 새 exe 시작
        subprocess.Popen([str(exe_path)], cwd=str(BASE_DIR))
        logger.info("새 에이전트 시작됨, 현재 프로세스 종료")
        time.sleep(1)
        import os
        os._exit(0)
    except Exception as e:
        logger.error(f"에이전트 업데이트 적용 실패: {e}")
        # 롤백: .old → 원래 이름
        try:
            if not exe_path.exists() and old_path.exists():
                old_path.rename(exe_path)
        except Exception:
            pass
    return False


def main():
    # 대기 중인 에이전트 업데이트 적용
    check_and_apply_pending()
    # 평문 API 키 자동 암호화
    auto_encrypt_config()
    # 설정 로드 (복호화)
    cfg = load_agent_config()
    agent = PickAgent(
        server_url=cfg["server_url"],
        api_key=cfg["api_key"],
    )
    agent.run()


if __name__ == "__main__":
    main()
