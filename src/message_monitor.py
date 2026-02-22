"""
카카오톡 채팅방 메시지 모니터링 메인 루프.

신규 메시지 감지 알고리즘: Tail Anchor 방식
  - 이전 스냅샷의 마지막 ANCHOR_LINES 줄을 앵커로 저장
  - 새 스냅샷에서 앵커 이후 내용만 신규 메시지로 처리
  - 앵커 미발견 시 경고 로그 후 해당 사이클 스킵

첫 실행 시 기존 메시지는 기준선으로만 사용 (중복 알림 방지).
"""
import sys
import threading
from pathlib import Path
from typing import Callable, List, Optional

# 프로젝트 루트를 sys.path에 추가 (python src/message_monitor.py 직접 실행 대응)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clipboard_reader import extract_chat_text
from src.logger_config import setup_logger
from src.message_parser import ChatMessage, parse_clipboard_text
from src.window_finder import get_chat_room_hwnd

logger = setup_logger("message_monitor")

ANCHOR_LINES = 10  # 앵커로 사용할 마지막 줄 수


# ---------------------------------------------------------------------------
# Tail Anchor 헬퍼
# ---------------------------------------------------------------------------

def _get_tail_anchor(text: str, n: int = ANCHOR_LINES) -> List[str]:
    """텍스트에서 비어있지 않은 마지막 n개 줄 반환."""
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[-n:] if len(lines) >= n else lines[:]


def _find_anchor_end_index(lines: List[str], anchor: List[str]) -> int:
    """
    lines 에서 anchor 전체 시퀀스의 마지막 줄 인덱스를 반환.
    발견하지 못하면 -1 반환.
    뒤에서부터 탐색하여 가장 최근 앵커 위치를 선택.
    """
    if not anchor:
        return -1

    anchor_stripped = [a.strip() for a in anchor]
    anchor_len = len(anchor_stripped)

    for i in range(len(lines) - 1, anchor_len - 2, -1):
        if lines[i].strip() == anchor_stripped[-1]:
            start = i - anchor_len + 1
            if start >= 0:
                candidate = [lines[j].strip() for j in range(start, i + 1)]
                if candidate == anchor_stripped:
                    return i
    return -1


def _extract_new_text(new_text: str, anchor: List[str]) -> Optional[str]:
    """
    new_text 에서 anchor 이후 부분만 반환.
    anchor가 없으면 new_text 전체 반환.
    anchor를 찾지 못하면 None 반환.
    """
    if not anchor:
        return new_text

    lines = new_text.splitlines()
    idx = _find_anchor_end_index(lines, anchor)

    if idx == -1:
        return None

    tail = lines[idx + 1 :]
    return "\n".join(tail)


# ---------------------------------------------------------------------------
# 기본 콜백
# ---------------------------------------------------------------------------

def default_on_new_message(msg: ChatMessage) -> None:
    """기본 메시지 핸들러: 로그에 출력."""
    logger.info(f"[신규] {msg.timestamp_str} {msg.sender}: {msg.content}")


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------

def run_monitor(
    room_name: str,
    poll_interval: float = 3.0,
    watch_sender: str = "",
    on_new_message: Callable[[ChatMessage], None] = default_on_new_message,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    카카오톡 채팅방을 주기적으로 폴링하여 신규 메시지를 감지·전달.

    Args:
        room_name:       모니터링할 단톡방 이름
        poll_interval:   폴링 간격 (초)
        watch_sender:    특정 송신자만 필터링 (빈 문자열이면 전체)
        on_new_message:  신규 메시지 수신 시 호출할 콜백
        stop_event:      외부에서 루프를 중지할 threading.Event
    """
    _stop = stop_event if stop_event is not None else threading.Event()

    if not room_name:
        logger.error("채팅방 이름이 설정되지 않았습니다.")
        return

    logger.info(f"모니터링 시작 | 채팅방='{room_name}' | 간격={poll_interval}초")
    if watch_sender:
        logger.info(f"송신자 필터: '{watch_sender}'")

    anchor: List[str] = []
    is_first_run = True

    while not _stop.is_set():
        try:
            # --- 창 탐색 ---
            hwnd = get_chat_room_hwnd(room_name)
            if hwnd is None:
                logger.warning(
                    f"채팅방 '{room_name}' 창 미발견. {poll_interval}초 후 재시도..."
                )
                _stop.wait(timeout=poll_interval)
                continue

            # --- 텍스트 추출 ---
            text = extract_chat_text(hwnd)
            if text is None:
                logger.warning("텍스트 추출 실패. 다음 사이클 재시도...")
                _stop.wait(timeout=poll_interval)
                continue

            # --- 첫 실행: 기준선 설정 ---
            if is_first_run:
                anchor = _get_tail_anchor(text)
                logger.info(f"기준선 설정 완료 (앵커 {len(anchor)}줄).")
                is_first_run = False
                _stop.wait(timeout=poll_interval)
                continue

            # --- 신규 텍스트 추출 ---
            new_text = _extract_new_text(text, anchor)
            if new_text is None:
                logger.warning("앵커를 찾을 수 없습니다. 이번 사이클 스킵.")
                _stop.wait(timeout=poll_interval)
                continue

            # --- 신규 메시지 파싱 및 콜백 ---
            if new_text.strip():
                new_messages = parse_clipboard_text(new_text)
                for msg in new_messages:
                    if watch_sender and msg.sender != watch_sender:
                        continue
                    on_new_message(msg)

            # --- 앵커 갱신 ---
            anchor = _get_tail_anchor(text)

        except Exception as exc:
            logger.exception(f"예기치 않은 오류: {exc}")

        _stop.wait(timeout=poll_interval)
