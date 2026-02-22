"""
테스트: 카카오톡 창 및 채팅방 HWND 탐색.

실행 방법:
    python -m tests.test_window_finder

전제 조건:
    - 카카오톡 PC 클라이언트가 실행 중이어야 함
    - .env 에 KAKAO_ROOM_NAME 이 설정되어 있어야 함
    - 해당 채팅방이 팝업 창으로 분리되어 있어야 함 (더블클릭)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.logger_config import setup_logger
from src.window_finder import (
    get_chat_room_hwnd,
    get_kakaotalk_main_hwnd,
    list_all_kakao_windows,
)

load_dotenv()
logger = setup_logger("test_window_finder")


def test_list_kakao_windows() -> bool:
    print("\n=== [1] 카카오톡 관련 창 목록 ===")
    windows = list_all_kakao_windows()
    if not windows:
        print("  카카오톡 관련 창이 발견되지 않았습니다.")
        print("  → 카카오톡이 실행 중인지 확인하세요.")
        return False

    for w in windows:
        print(
            f"  HWND={w['hwnd']:<10} 클래스={w['class']:<25} "
            f"표시={str(w['visible']):<5} 제목='{w['title']}'"
        )
    return True


def test_main_hwnd() -> bool:
    print("\n=== [2] 카카오톡 메인 창 탐색 ===")
    hwnd = get_kakaotalk_main_hwnd()
    if hwnd:
        print(f"  메인 창 발견: HWND={hwnd}")
        return True
    print("  메인 창을 찾을 수 없습니다. 카카오톡이 실행 중인지 확인하세요.")
    return False


def test_chat_room_hwnd() -> bool:
    room_name = os.getenv("KAKAO_ROOM_NAME", "").strip()
    print(f"\n=== [3] 채팅방 팝업 창 탐색: '{room_name}' ===")

    if not room_name:
        print("  KAKAO_ROOM_NAME 이 .env 에 설정되어 있지 않습니다.")
        return False

    hwnd = get_chat_room_hwnd(room_name)
    if hwnd:
        print(f"  채팅방 창 발견: HWND={hwnd}")
        return True

    print(f"  채팅방 '{room_name}'을 찾을 수 없습니다.")
    print("  → 채팅방을 더블클릭하여 팝업 창으로 분리했는지 확인하세요.")
    return False


if __name__ == "__main__":
    print("카카오톡 창 탐색 테스트 시작")

    r1 = test_list_kakao_windows()
    r2 = test_main_hwnd()
    r3 = test_chat_room_hwnd()

    print(f"\n결과: 창 목록={r1}  메인창={r2}  채팅방={r3}")

    if all([r1, r2, r3]):
        print("모든 테스트 통과!")
    else:
        print("일부 테스트 실패. 위 안내를 참고하세요.")
        sys.exit(1)
