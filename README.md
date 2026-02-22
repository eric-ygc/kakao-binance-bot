# 카카오 모니터 — 카카오톡 메시지 기반 바이낸스 자동 입력 봇

PC 카카오톡 단톡방을 실시간 모니터링하여 **영문+숫자 8자리 코드**가 수신되면
바이낸스 브라우저 입력창에 자동으로 입력하는 Windows 전용 프로그램.

---

## 개발 현황

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 | 카카오톡 메시지 추출 엔진 | ✅ 완료 |
| Phase 2 | GUI 앱 + exe 실행파일 | ✅ 완료 |
| Phase 3 | 8자리 코드 캐치 패널 | ✅ 완료 |
| Phase 4 | 바이낸스 브라우저 자동 입력 | 🔲 미착수 |

---

## 요구 사항

- **OS:** Windows 11
- **Python:** 3.12 이상
- **카카오톡:** PC 버전, 채팅방을 **팝업 분리** 상태로 실행 (채팅방 더블클릭)

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 실행

### GUI 앱 (개발/소스 실행)

```bash
python app.py
```

### 배포용 exe (터미널 불필요)

```
dist\카카오모니터.exe
```

---

## 사용 방법

1. 카카오톡 채팅방을 **팝업으로 분리** (채팅방 더블클릭)
2. 앱 실행 후 **채팅방 이름** 입력
3. 필요 시 발신자 필터, 폴링 간격 조정
4. **[▶ 모니터링 시작]** 클릭

수신 메시지 중 `^[A-Za-z0-9]{8}$` 패턴의 코드가 캐치되면 상단 패널에 크게 표시됩니다.

---

## 파일 구조

```
kakao-binance-bot/
├── app.py                   # GUI 진입점
├── config.json              # 설정 저장 (자동 생성)
├── requirements.txt
├── dist/
│   └── 카카오모니터.exe
├── src/
│   ├── window_finder.py     # 카카오톡 창 HWND 탐색
│   ├── clipboard_reader.py  # 클립보드 방식 텍스트 추출
│   ├── message_parser.py    # 신형식/구형식 메시지 파싱
│   ├── message_monitor.py   # 폴링 루프
│   └── logger_config.py     # UTF-8 로거
├── tests/
│   ├── test_message_parser.py   # 독립 실행 가능
│   ├── test_window_finder.py    # 카카오톡 실행 필요
│   └── test_clipboard_reader.py # 카카오톡 실행 필요
└── docs/
    └── plan.md              # 개발 계획서
```

---

## 테스트

```bash
# 카카오톡 없이 파서 단위 테스트
python -m tests.test_message_parser

# 카카오톡 실행 + 팝업 분리 상태에서
python -m tests.test_window_finder
python -m tests.test_clipboard_reader
```

---

## 기술 메모

- 카카오톡은 Direct2D 커스텀 렌더러 사용 → Win32 텍스트 컨트롤 접근 불가
- **클립보드 방식** (Ctrl+A → Ctrl+C) 으로 텍스트 추출
- Windows 11 포그라운드 차단 → `AllowSetForegroundWindow(-1)` 선행 호출
- 클립보드 변경 감지 → `GetClipboardSequenceNumber` 폴링 (최대 3초)

자세한 내용은 [`docs/plan.md`](docs/plan.md) 참고.
