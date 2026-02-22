"""
카카오톡 클립보드 원문 → ChatMessage 리스트 파싱.

지원 형식:
  신형식: "오전 10:30 홍길동\\n메시지내용"  (시간+이름 한 줄, 내용 다음 줄)
  구형식: "[홍길동] [오전 10:30] 메시지내용" (한 줄)

예외 처리:
  날짜 구분선, 시스템 메시지(입/퇴장·첨부파일 표시·삭제 메시지) 무시.
"""
import re
from dataclasses import dataclass
from typing import List

from src.logger_config import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    sender: str
    content: str
    timestamp_str: str  # 원본 타임스탬프 문자열 ("오전 10:30" 등)
    raw_line: str       # 파싱에 사용된 원본 줄(들)


# ---------------------------------------------------------------------------
# 정규식 패턴
# ---------------------------------------------------------------------------

# 신형식 헤더: "오전 10:30 홍길동"
_NEW_HEADER = re.compile(r"^(오전|오후)\s+(\d{1,2}:\d{2})\s+(.+)$")

# 구형식 한 줄: "[홍길동] [오전 10:30] 메시지"
_OLD_LINE = re.compile(r"^\[(.+?)\]\s*\[(오전|오후)\s+(\d{1,2}:\d{2})\]\s*(.+)$")

# 날짜 구분선: "2024년 1월 15일 월요일"
_DATE_LINE = re.compile(r"^\d{4}년\s+\d{1,2}월\s+\d{1,2}일")

# 시스템 메시지 패턴 목록
_SYSTEM_PATTERNS: list[re.Pattern] = [
    re.compile(r"^.+님이 .+를 초대했습니다\.?$"),
    re.compile(r"^.+님이 나갔습니다\.?$"),
    re.compile(r"^.+님이 입장했습니다\.?$"),
    re.compile(r"^채팅방 참여 코드가 .+$"),
    re.compile(r"^이모티콘$"),
    re.compile(r"^사진$"),
    re.compile(r"^동영상$"),
    re.compile(r"^파일$"),
    re.compile(r"^삭제된 메시지입니다\.?$"),
    re.compile(r"^음성메시지$"),
]


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _is_date_line(line: str) -> bool:
    return bool(_DATE_LINE.match(line))


def _is_system_line(line: str) -> bool:
    return any(p.match(line) for p in _SYSTEM_PATTERNS)


def _parse_old_format(lines: List[str]) -> List[ChatMessage]:
    """구형식: [이름] [시간] 메시지 한 줄씩 파싱."""
    messages: List[ChatMessage] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _is_date_line(stripped) or _is_system_line(stripped):
            continue
        m = _OLD_LINE.match(stripped)
        if m:
            messages.append(
                ChatMessage(
                    sender=m.group(1).strip(),
                    content=m.group(4).strip(),
                    timestamp_str=f"{m.group(2)} {m.group(3)}",
                    raw_line=stripped,
                )
            )
    return messages


def _parse_new_format(lines: List[str]) -> List[ChatMessage]:
    """
    신형식: 헤더 줄(오전/오후 HH:MM 이름) 다음에 내용 줄(들)이 오는 구조.
    다음 헤더 또는 날짜 구분선이 나오면 현재 메시지 종료.
    """
    messages: List[ChatMessage] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or _is_date_line(line):
            i += 1
            continue

        m = _NEW_HEADER.match(line)
        if m:
            am_pm, time_str, sender = m.group(1), m.group(2), m.group(3).strip()
            timestamp_str = f"{am_pm} {time_str}"
            raw_header = line

            # 내용 줄 수집
            content_lines: List[str] = []
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                # 다음 메시지 헤더 또는 날짜 구분선이면 중단
                if _NEW_HEADER.match(next_stripped) or _is_date_line(next_stripped):
                    break
                # 시스템 메시지 줄은 내용에 포함하지 않고 건너뜀
                if next_stripped and _is_system_line(next_stripped):
                    i += 1
                    continue
                # 빈 줄은 보존 (멀티라인 메시지 보존)
                content_lines.append(lines[i].rstrip())
                i += 1

            # 앞뒤 빈 줄 제거 후 조합
            content = "\n".join(content_lines).strip()

            if content and not _is_system_line(content):
                messages.append(
                    ChatMessage(
                        sender=sender,
                        content=content,
                        timestamp_str=timestamp_str,
                        raw_line=f"{raw_header}\n{content}",
                    )
                )
        else:
            i += 1

    return messages


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def parse_clipboard_text(text: str) -> List[ChatMessage]:
    """
    클립보드 텍스트를 ChatMessage 리스트로 파싱.
    신형식과 구형식을 자동 감지하여 처리.

    Args:
        text: 카카오톡 Ctrl+A Ctrl+C 로 얻은 원문 문자열

    Returns:
        파싱된 ChatMessage 리스트 (시스템 메시지·날짜 구분선 제외)
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()

    # 구형식 감지: 유효한 첫 메시지 줄이 [이름] [시간] 형식인지 확인
    for line in lines:
        stripped = line.strip()
        if stripped and not _is_date_line(stripped) and not _is_system_line(stripped):
            if _OLD_LINE.match(stripped):
                logger.debug("구형식 감지")
                messages = _parse_old_format(lines)
            else:
                logger.debug("신형식 감지")
                messages = _parse_new_format(lines)
            break
    else:
        messages = []

    logger.debug(f"파싱 완료: {len(messages)}개 메시지")
    return messages
