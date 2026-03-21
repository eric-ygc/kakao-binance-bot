# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# GUI 앱 실행
python app.py

# 단위 테스트 (카카오톡 불필요)
python -m tests.test_message_parser

# 카카오톡 실행 + 팝업 분리 상태에서 실행
python -m tests.test_window_finder
python -m tests.test_clipboard_reader

# exe 빌드
pyinstaller --onefile --windowed --name 카카오모니터 app.py
```

## Architecture

### 데이터 흐름

```
카카오톡 팝업 창
    └─► window_finder.py   : EnumWindows → HWND 획득
    └─► clipboard_reader.py: 창 전경화 → 채팅영역 클릭 → Ctrl+A/C → 클립보드 텍스트
    └─► message_parser.py  : 텍스트 → ChatMessage 리스트
    └─► message_monitor.py : Tail Anchor 폴링 루프 → on_new_message 콜백
    └─► app.py             : queue.Queue → tkinter GUI 업데이트
```

### 핵심 컴포넌트

**`src/message_monitor.py` — 폴링 루프**
- `run_monitor()` 함수가 별도 스레드에서 실행됨
- **Tail Anchor 방식**: 이전 스냅샷 마지막 10줄을 앵커로 저장 → 다음 스냅샷에서 앵커 이후 텍스트만 신규 메시지로 처리
- 첫 실행 시 기존 메시지는 기준선으로만 사용 (중복 알림 방지)
- `stop_event: threading.Event`로 외부에서 루프 종료

**`src/clipboard_reader.py` — 클립보드 추출**
- 카카오톡은 Direct2D 렌더러라 Win32 컨트롤 텍스트 접근 불가 → 클립보드 방식 필수
- Windows 11 포그라운드 차단 → `AllowSetForegroundWindow(-1)` 선행
- Ctrl+A가 입력창을 선택하는 문제 → 창 상단 35% 지점 클릭 후 실행
- 클립보드 업데이트 감지: `GetClipboardSequenceNumber` 폴링 (최대 3초)

**`src/message_parser.py` — 메시지 파싱**
- `ChatMessage(sender, content, timestamp_str, raw_line)` 데이터클래스
- 신형식(`오전 10:30 홍길동\n내용`)과 구형식(`[홍길동] [오전 10:30] 내용`) 자동 감지
- 날짜 구분선, 시스템 메시지(입퇴장·첨부파일·이모티콘), 삭제 메시지 자동 제외
- `parse_clipboard_text(text) → List[ChatMessage]` 가 공개 API

**`src/window_finder.py` — 창 탐색**
- 카카오톡 창 클래스명: `EVA_Window_Dblclk` (메인창·팝업 공통)
- 메인창 제목 == `'카카오톡'`, 채팅방 팝업 제목 == 단톡방 이름
- 채팅방은 반드시 팝업 분리 상태여야 함 (채팅방 더블클릭)

**`app.py` — tkinter GUI**
- 스레드 분리: 모니터링 스레드 ↔ GUI 스레드 간 `queue.Queue`로 통신
- `root.after(200, _poll_queue)`로 200ms마다 큐를 드레인
- 9자리 영숫자 코드 감지: `^[A-Za-z0-9]{8}$`
- exe 실행 시 `sys.frozen` 플래그로 `BASE_DIR` 경로 전환 (config.json 위치)
- 설정은 `config.json`에 자동 저장/복원

### 카카오톡 윈도우 클래스 (실측값)

| 구분 | 클래스명 | 창 제목 |
|------|----------|---------|
| 메인창 | `EVA_Window_Dblclk` | `카카오톡` |
| 채팅방 팝업 | `EVA_Window_Dblclk` | 단톡방 이름 |

디버깅 시 `window_finder.list_all_kakao_windows()`로 모든 카카오 관련 창 확인 가능.
