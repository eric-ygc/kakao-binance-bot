"""
카카오톡 채팅방 팝업에서 Ctrl+A / Ctrl+C 로 전체 내역을 클립보드로 추출.

주요 함정 대응:
  - Windows 11 SetForegroundWindow 제한: AllowSetForegroundWindow(-1) 우회
  - Ctrl+A가 입력창을 잡는 문제: 타이틀바 바로 아래(창 상단 8% 지점)를 클릭 → 이미지 클릭 방지
  - 클립보드 경쟁 조건: GetClipboardSequenceNumber 폴링으로 업데이트 감지
"""
import ctypes
import time
from typing import Optional

import win32api
import win32clipboard
import win32con
import win32gui
from pywinauto import keyboard

from src.logger_config import setup_logger

logger = setup_logger(__name__)

CLIPBOARD_WAIT_TIMEOUT = 3.0   # 클립보드 업데이트 최대 대기 시간 (초)
CLIPBOARD_POLL_INTERVAL = 0.05  # 폴링 간격 (초)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _allow_set_foreground() -> None:
    """Windows 11 포커스 잠금 우회 (ASFW_ANY = -1)."""
    ctypes.windll.user32.AllowSetForegroundWindow(-1)


def _get_clipboard_seq() -> int:
    return ctypes.windll.user32.GetClipboardSequenceNumber()


def _click_chat_area(hwnd: int) -> None:
    """
    채팅 내역 영역을 클릭하여 Ctrl+A 가 입력창 대신 내역을 선택하도록 함.
    타이틀바 바로 아래(세로 8% 지점)를 클릭한다.
    → 최근 메시지(이미지 포함)는 창 하단에 쌓이므로 상단 클릭 시 이미지 선택 위험 없음.
    """
    rect = win32gui.GetWindowRect(hwnd)
    x = rect[0] + (rect[2] - rect[0]) // 2
    y = rect[1] + int((rect[3] - rect[1]) * 0.08)

    ctypes.windll.user32.SetCursorPos(x, y)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    time.sleep(0.1)


def _bring_to_foreground(hwnd: int) -> bool:
    """창을 전경으로 가져온다. 실패 시 False 반환."""
    try:
        _allow_set_foreground()

        if win32gui.IsIconic(hwnd):  # 최소화된 경우 복원
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)

        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return True
    except Exception as exc:
        logger.warning(f"창 전경화 실패: {exc}")
        return False


def _read_clipboard_unicode() -> Optional[str]:
    """클립보드에서 CF_UNICODETEXT 형식으로 텍스트를 읽는다."""
    try:
        win32clipboard.OpenClipboard(0)
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        logger.warning(f"클립보드 읽기 실패: {exc}")
    return None


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def extract_chat_text(hwnd: int) -> Optional[str]:
    """
    채팅방 팝업 창(hwnd)에서 전체 채팅 내역을 클립보드로 추출하여 반환.

    Returns:
        추출된 유니코드 문자열. 실패 시 None.
    """
    if not win32gui.IsWindow(hwnd):
        logger.error(f"유효하지 않은 HWND: {hwnd}")
        return None

    # 1. 창 전경화
    if not _bring_to_foreground(hwnd):
        return None

    # 2. 채팅 내역 영역 클릭
    _click_chat_area(hwnd)
    time.sleep(0.1)

    # 3. 현재 클립보드 시퀀스 번호 기록
    seq_before = _get_clipboard_seq()

    # 4. Ctrl+A → Ctrl+C
    try:
        keyboard.send_keys("^a")
        time.sleep(0.2)
        keyboard.send_keys("^c")
    except Exception as exc:
        logger.warning(f"키 전송 실패: {exc}")
        return None

    # 5. 클립보드 업데이트 대기 (최대 CLIPBOARD_WAIT_TIMEOUT 초)
    deadline = time.time() + CLIPBOARD_WAIT_TIMEOUT
    updated = False
    while time.time() < deadline:
        time.sleep(CLIPBOARD_POLL_INTERVAL)
        if _get_clipboard_seq() != seq_before:
            updated = True
            break

    if not updated:
        logger.warning("클립보드 업데이트 타임아웃 (Ctrl+C가 적용되지 않았을 수 있음)")
        return None

    # 6. 텍스트 읽기
    text = _read_clipboard_unicode()
    if text:
        logger.debug(f"클립보드 추출 성공: {len(text)}자")
    else:
        logger.warning("클립보드에서 텍스트를 읽지 못했습니다.")

    return text
