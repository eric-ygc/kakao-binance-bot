# 개발 계획서: 카카오톡 메시지 기반 바이낸스 자동 입력 시스템

> 최종 업데이트: 2026-02-22

## 1. 프로젝트 개요

**목표:** PC 카카오톡 특정 단톡방의 메시지를 실시간 모니터링하여,
영문+숫자 8자리 코드가 수신되면 이미 로그인된 바이낸스 브라우저의
특정 입력창에 자동으로 입력하고 버튼을 클릭하는 프로그램.

**핵심 도구:** Python, tkinter, PyWinAuto, pyperclip, Selenium (Chrome Debugging)

---

## 2. 개발 단계 (Milestones)

### Phase 1: 카카오톡 메시지 추출 엔진 ✅ 완료

**목표:** 실행 중인 PC 카카오톡 채팅방에서 텍스트를 실시간 추출

**기술 결정:**
- 카카오톡은 Direct2D 커스텀 렌더러 사용 → Win32 텍스트 컨트롤에 접근 불가
- **클립보드 방식 채택**: Ctrl+A → Ctrl+C로 전체 대화 복사
- 채팅방은 반드시 **팝업 분리** 형태 필요 (더블클릭으로 별도 창)
- 창 클래스명: 메인창 `EVA_Window_Dblclk`, 팝업 `EVA_Window`

**구현 파일:**

| 파일 | 역할 |
|------|------|
| `src/window_finder.py` | EnumWindows로 채팅방 HWND 탐색 |
| `src/clipboard_reader.py` | AllowSetForegroundWindow + Ctrl+A/C 텍스트 추출 |
| `src/message_parser.py` | 신형식/구형식 파싱, ChatMessage 데이터클래스 |
| `src/message_monitor.py` | Tail Anchor 폴링 루프, stop_event 지원 |
| `src/logger_config.py` | UTF-8 파일+콘솔 핸들러 (cp949 대응) |

**파싱 형식:**
- 신형식: `오전 10:30 홍길동\n메시지내용`
- 구형식: `[홍길동] [오전 10:30] 메시지내용`
- 날짜 구분선 / 시스템 메시지 / 첨부파일 표시 자동 제외

**주요 해결 이슈:**
- Windows 11 SetForegroundWindow 차단 → `AllowSetForegroundWindow(-1)` 선행
- Ctrl+A가 입력창 선택 → 창 상단 35% 지점 클릭 후 실행
- 클립보드 타이밍 → `GetClipboardSequenceNumber` 폴링 (최대 3초)

---

### Phase 2: GUI 앱 + 실행파일 ✅ 완료

**목표:** 터미널 없이 더블클릭으로 실행 가능한 Windows 앱

**구현:**
- `app.py` — tkinter 기반 GUI
- `dist/카카오모니터.exe` — PyInstaller 단일 파일 (16 MB)
- `config.json` — 설정 자동 저장/복원 (exe 옆에 생성)

**GUI 구성:**
```
┌──────────────────────────────────────┐
│ 설정 (채팅방 이름 / 폴링 간격 / 발신자 필터 / 항상 위) │
├──────────────────────────────────────┤
│ [▶ 모니터링 시작] [■ 중지] [로그지우기] │
├──────────────────────────────────────┤
│ 캐치된 코드 패널                      │
├──────────────────────────────────────┤
│ 전체 메시지 로그                      │
├──────────────────────────────────────┤
│ 상태바                               │
└──────────────────────────────────────┘
```

**스레드 아키텍처:**
- 모니터링: `threading.Thread(daemon=True)` + `stop_event`
- GUI 전달: `queue.Queue` + `root.after(200, _poll_queue)`
- exe 경로: `sys.frozen` 플래그로 `sys.executable.parent` 사용

---

### Phase 3: 코드 캐치 ✅ 완료

**목표:** 수신 메시지 중 특정 패턴(영문+숫자 8자리)만 별도 강조 표시

**규칙:** 정규식 `^[A-Za-z0-9]{8}$` 정확히 일치 시 캐치

**캐치 패널:**
- 최신 코드: 36pt 대형 노란색 폰트
- 메타 정보: 수신 시간 + 발신자
- 이전 코드: 최대 8개 히스토리 한 줄 표시

**로그 연동:**
- 전체 메시지는 하단 로그에 그대로 누적
- 캐치된 코드는 로그에서 노란색 + ★ 강조

---

### Phase 4: 바이낸스 브라우저 자동 입력 🔲 미착수

**목표:** 캐치된 8자리 코드를 바이낸스 입력창에 자동 입력 + 버튼 클릭

**기술 스택:** Selenium (Chrome Remote Debugging, 포트 9222)
- API Key 미사용 — DOM 직접 제어 방식

**작업 항목:**
- [ ] 크롬 디버깅 포트(9222) 실행 스크립트
- [ ] Selenium으로 현재 열린 바이낸스 탭 연결
- [ ] 입력창 DOM 요소 탐색 (`driver.find_element`)
- [ ] `send_keys(code)` 입력 + 버튼 클릭
- [ ] GUI 앱 연동 — 코드 캐치 시 자동 트리거
- [ ] `requirements.txt`에 `selenium` 추가 및 exe 재빌드

---

## 3. 기술 스택

| 구분 | 라이브러리 | 용도 |
|------|-----------|------|
| 현재 사용 | pywinauto | 카카오톡 창 제어 |
| 현재 사용 | pywin32 | Windows API (클립보드, 포그라운드) |
| 현재 사용 | pyperclip | 클립보드 읽기 |
| 현재 사용 | tkinter | GUI |
| 현재 사용 | PyInstaller | exe 패키징 |
| Phase 4 예정 | selenium | 바이낸스 브라우저 제어 |

**환경:** Windows 11, Python 3.12

---

## 4. 파일 구조

```
kakao-binance-bot/
├── app.py                   # GUI 진입점
├── config.json              # 설정 저장 (자동 생성)
├── requirements.txt
├── dist/
│   └── 카카오모니터.exe
├── src/
│   ├── logger_config.py
│   ├── window_finder.py
│   ├── clipboard_reader.py
│   ├── message_parser.py
│   └── message_monitor.py
├── tests/
│   ├── test_message_parser.py   # 독립 실행 가능
│   ├── test_window_finder.py    # 카카오톡 실행 필요
│   └── test_clipboard_reader.py # 카카오톡 실행 필요
└── docs/
    └── plan.md
```

---

## 5. 실행

```bash
# GUI 앱 (개발 중)
python app.py

# 배포용 exe
dist\카카오모니터.exe

# 단위 테스트
python -m tests.test_message_parser
```
