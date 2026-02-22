"""
카카오톡 창 핸들(HWND) 탐색.

실측 결과: 카카오톡 PC의 메인창과 채팅방 팝업 모두 EVA_Window_Dblclk 클래스를 사용.
창 제목으로 구분:
  - 메인창:     제목 == '카카오톡'
  - 채팅방 팝업: 제목 == 단톡방 이름 (팝업으로 분리 시)
"""
from typing import Optional

import win32gui

from src.logger_config import setup_logger

logger = setup_logger(__name__)

KAKAO_CLASS = "EVA_Window_Dblclk"   # 메인창과 채팅방 팝업 공통 클래스
KAKAO_MAIN_TITLE = "카카오톡"        # 메인창 식별 제목


def get_kakaotalk_main_hwnd() -> Optional[int]:
    """카카오톡 메인 창('카카오톡' 제목) HWND 반환. 없으면 None."""
    result: list[int] = []

    def _cb(hwnd: int, _) -> None:
        if (
            win32gui.GetClassName(hwnd) == KAKAO_CLASS
            and win32gui.IsWindowVisible(hwnd)
            and win32gui.GetWindowText(hwnd) == KAKAO_MAIN_TITLE
        ):
            result.append(hwnd)

    win32gui.EnumWindows(_cb, None)

    if result:
        logger.debug(f"카카오톡 메인 창 발견: HWND={result[0]}")
        return result[0]

    logger.warning("카카오톡 메인 창을 찾을 수 없습니다.")
    return None


def get_chat_room_hwnd(room_name: str) -> Optional[int]:
    """
    특정 단톡방 팝업 창 HWND 반환.
    EVA_Window_Dblclk 클래스 중 제목에 room_name이 포함된 창을 탐색.
    없으면 None.
    """
    result: list[tuple[int, str]] = []

    def _cb(hwnd: int, _) -> None:
        if win32gui.GetClassName(hwnd) == KAKAO_CLASS:
            title = win32gui.GetWindowText(hwnd)
            if (
                room_name in title
                and title != KAKAO_MAIN_TITLE   # 메인창 제외
                and win32gui.IsWindowVisible(hwnd)
            ):
                result.append((hwnd, title))

    win32gui.EnumWindows(_cb, None)

    if result:
        hwnd, title = result[0]
        logger.debug(f"채팅방 창 발견: HWND={hwnd}, 제목='{title}'")
        return hwnd

    logger.warning(
        f"채팅방 '{room_name}'을 찾을 수 없습니다. "
        "팝업 창(더블클릭으로 분리)으로 열려 있는지 확인하세요."
    )
    return None


def list_all_kakao_windows() -> list[dict]:
    """디버깅용: 카카오톡 관련 모든 창 정보 목록 반환."""
    windows: list[dict] = []

    def _cb(hwnd: int, _) -> None:
        class_name = win32gui.GetClassName(hwnd)
        if "EVA" in class_name or "KakaoTalk" in class_name:
            windows.append(
                {
                    "hwnd": hwnd,
                    "class": class_name,
                    "title": win32gui.GetWindowText(hwnd),
                    "visible": bool(win32gui.IsWindowVisible(hwnd)),
                }
            )

    win32gui.EnumWindows(_cb, None)
    return windows
