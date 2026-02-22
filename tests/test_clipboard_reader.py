"""
테스트: 카카오톡 채팅방에서 클립보드 텍스트 추출.

실행 방법:
    python -m tests.test_clipboard_reader

전제 조건:
    - 카카오톡 PC 클라이언트가 실행 중이어야 함
    - .env 에 KAKAO_ROOM_NAME 이 설정되어 있어야 함
    - 해당 채팅방이 팝업 창으로 분리되어 있어야 함

주의:
    이 테스트 실행 중 카카오톡 창이 잠시 활성화(전경화)됩니다.
    실행 중에는 다른 창을 클릭하지 마세요.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.clipboard_reader import extract_chat_text
from src.logger_config import setup_logger
from src.window_finder import get_chat_room_hwnd

load_dotenv()
logger = setup_logger("test_clipboard_reader")

PREVIEW_CHARS = 500  # 미리보기로 출력할 마지막 글자 수


def test_extract_chat_text() -> bool:
    room_name = os.getenv("KAKAO_ROOM_NAME", "").strip()
    print(f"\n=== 클립보드 추출 테스트: '{room_name}' ===")

    if not room_name:
        print("  KAKAO_ROOM_NAME 이 .env 에 설정되어 있지 않습니다.")
        return False

    hwnd = get_chat_room_hwnd(room_name)
    if not hwnd:
        print(f"  채팅방 '{room_name}' 창을 찾을 수 없습니다.")
        print("  → 팝업 창으로 분리되어 있는지 확인하세요.")
        return False

    print(f"  채팅방 HWND={hwnd}")
    print("  텍스트 추출 중... (창이 잠시 활성화됩니다)")

    text = extract_chat_text(hwnd)

    if text is None:
        print("  텍스트 추출 실패!")
        return False

    print(f"\n  추출 성공: 총 {len(text)}자")

    # 마지막 PREVIEW_CHARS 자 미리보기
    preview = text[-PREVIEW_CHARS:] if len(text) > PREVIEW_CHARS else text
    print(f"\n--- 마지막 {PREVIEW_CHARS}자 미리보기 ---")
    print(preview)
    print("-------------------------------")

    # 타임스탬프 패턴 포함 여부 검증
    has_timestamp = bool(re.search(r"(오전|오후)\s+\d{1,2}:\d{2}", text))
    print(f"\n  타임스탬프 패턴 발견: {has_timestamp}")
    if not has_timestamp:
        print("  경고: 타임스탬프 패턴이 없습니다. 채팅 내역이 없거나 형식이 다를 수 있습니다.")

    return True


if __name__ == "__main__":
    print("클립보드 추출 테스트 시작")
    result = test_extract_chat_text()

    if result:
        print("\n테스트 통과!")
    else:
        print("\n테스트 실패!")
        sys.exit(1)
