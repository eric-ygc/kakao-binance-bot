"""
테스트: 메시지 파서 단위 테스트 (하드코딩 샘플 기반).

실행 방법:
    python -m tests.test_message_parser

카카오톡이 실행되어 있지 않아도 실행 가능.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger_config import setup_logger
from src.message_parser import ChatMessage, parse_clipboard_text

logger = setup_logger("test_message_parser")


# ---------------------------------------------------------------------------
# 테스트 샘플 데이터
# ---------------------------------------------------------------------------

NEW_FORMAT_SAMPLE = """\
2024년 1월 15일 월요일
오전 10:30 홍길동
안녕하세요
오전 10:31 이순신
네 안녕하세요
오전 10:32 홍길동
오늘 날씨가 좋네요
이모티콘
오후 2:15 김철수
저도 좋네요
삭제된 메시지입니다."""

OLD_FORMAT_SAMPLE = """\
2024년 1월 15일 월요일
[홍길동] [오전 10:30] 안녕하세요
[이순신] [오전 10:31] 네 안녕하세요
[홍길동] [오전 10:32] 오늘 날씨가 좋네요
[김철수] [오후 2:15] 저도 좋네요"""

MULTILINE_SAMPLE = """\
오전 9:00 홍길동
첫째 줄
둘째 줄
셋째 줄
오전 9:05 이순신
짧은 메시지"""

TRADING_SIGNAL_SAMPLE = """\
오전 10:00 신호발생자
바이낸스 매수 BTC 0.1"""


# ---------------------------------------------------------------------------
# 개별 테스트 함수
# ---------------------------------------------------------------------------

def test_new_format() -> bool:
    print("\n=== [1] 신형식 파싱 ===")
    messages = parse_clipboard_text(NEW_FORMAT_SAMPLE)

    for msg in messages:
        print(f"  [{msg.timestamp_str}] {msg.sender}: {msg.content}")

    assert len(messages) >= 3, f"예상 3개 이상, 실제 {len(messages)}개"

    hong_msgs = [m for m in messages if m.sender == "홍길동"]
    assert hong_msgs, "홍길동 메시지 없음"
    assert hong_msgs[0].content == "안녕하세요", (
        f"첫 번째 홍길동 메시지 내용 불일치: '{hong_msgs[0].content}'"
    )
    assert hong_msgs[0].timestamp_str == "오전 10:30", (
        f"타임스탬프 불일치: '{hong_msgs[0].timestamp_str}'"
    )

    print(f"  → {len(messages)}개 파싱 완료")
    return True


def test_old_format() -> bool:
    print("\n=== [2] 구형식 파싱 ===")
    messages = parse_clipboard_text(OLD_FORMAT_SAMPLE)

    for msg in messages:
        print(f"  [{msg.timestamp_str}] {msg.sender}: {msg.content}")

    assert len(messages) == 4, f"예상 4개, 실제 {len(messages)}개"
    assert messages[0].sender == "홍길동", f"첫 송신자 불일치: '{messages[0].sender}'"
    assert messages[0].content == "안녕하세요", f"첫 내용 불일치: '{messages[0].content}'"
    assert messages[1].sender == "이순신", f"두 번째 송신자 불일치: '{messages[1].sender}'"
    assert messages[3].sender == "김철수", f"마지막 송신자 불일치: '{messages[3].sender}'"

    print(f"  → {len(messages)}개 파싱 완료")
    return True


def test_multiline_content() -> bool:
    print("\n=== [3] 멀티라인 내용 파싱 ===")
    messages = parse_clipboard_text(MULTILINE_SAMPLE)

    for msg in messages:
        print(f"  [{msg.timestamp_str}] {msg.sender}: {repr(msg.content)}")

    assert len(messages) == 2, f"예상 2개, 실제 {len(messages)}개"
    assert "첫째 줄" in messages[0].content, "첫째 줄 누락"
    assert "둘째 줄" in messages[0].content, "둘째 줄 누락"
    assert "셋째 줄" in messages[0].content, "셋째 줄 누락"
    assert messages[1].content == "짧은 메시지", (
        f"두 번째 메시지 내용 불일치: '{messages[1].content}'"
    )

    print("  → 멀티라인 파싱 성공")
    return True


def test_empty_input() -> bool:
    print("\n=== [4] 빈 입력 처리 ===")
    assert parse_clipboard_text("") == [], "빈 문자열에서 메시지 반환됨"
    assert parse_clipboard_text("   \n\n  ") == [], "공백만 있는 입력에서 메시지 반환됨"
    print("  → 빈 입력 정상 처리")
    return True


def test_trading_signal() -> bool:
    print("\n=== [5] 트레이딩 시그널 메시지 파싱 ===")
    messages = parse_clipboard_text(TRADING_SIGNAL_SAMPLE)

    for msg in messages:
        print(f"  [{msg.timestamp_str}] {msg.sender}: {msg.content}")

    assert len(messages) == 1, f"예상 1개, 실제 {len(messages)}개"
    assert messages[0].sender == "신호발생자", (
        f"송신자 불일치: '{messages[0].sender}'"
    )
    assert messages[0].content == "바이낸스 매수 BTC 0.1", (
        f"내용 불일치: '{messages[0].content}'"
    )
    assert messages[0].timestamp_str == "오전 10:00", (
        f"타임스탬프 불일치: '{messages[0].timestamp_str}'"
    )

    print("  → 트레이딩 시그널 파싱 성공")
    return True


def test_system_messages_excluded() -> bool:
    print("\n=== [6] 시스템 메시지 제외 확인 ===")
    sample = """\
2024년 2월 1일 목요일
홍길동님이 이순신를 초대했습니다.
오전 8:00 홍길동
첫 메시지
홍길동님이 나갔습니다.
오전 8:01 이순신
두 번째 메시지"""

    messages = parse_clipboard_text(sample)
    for msg in messages:
        print(f"  [{msg.timestamp_str}] {msg.sender}: {msg.content}")

    senders = [m.sender for m in messages]
    assert "홍길동" in senders, "홍길동 메시지 없음"
    assert "이순신" in senders, "이순신 메시지 없음"

    # 시스템 메시지가 sender로 잡히지 않아야 함
    for msg in messages:
        assert "님이" not in msg.sender, f"시스템 메시지가 파싱됨: {msg}"

    print(f"  → {len(messages)}개 파싱 (시스템 메시지 제외 확인)")
    return True


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("메시지 파서 단위 테스트 시작")

    tests = [
        ("신형식 파싱", test_new_format),
        ("구형식 파싱", test_old_format),
        ("멀티라인 내용", test_multiline_content),
        ("빈 입력 처리", test_empty_input),
        ("트레이딩 시그널", test_trading_signal),
        ("시스템 메시지 제외", test_system_messages_excluded),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS: {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL: {name} — {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {name} — {type(e).__name__}: {e}")

    print(f"\n결과: {passed}개 통과 / {failed}개 실패 / 총 {passed + failed}개")

    if failed > 0:
        sys.exit(1)
    else:
        print("모든 테스트 통과!")
