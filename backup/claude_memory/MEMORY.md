# 프로젝트 메모리

## 프로젝트 개요
- **앱 이름**: 픽보조 (kakao-binance-bot)
- **목적**: 카카오톡에서 픽 코드 감지 → dsj44.com 다계정 자동 입력
- **진입점**: `main.py` (고정픽 + 보너스픽 탭 통합)
- **빌드**: `build.bat` (API/Selenium 선택 빌드) 또는 수동 pyinstaller
- **현재 버전**: v1.5.6 (API) / v1.4.6 (Selenium)
- **Selenium 복원 태그**: `v1.4-selenium`

## 핵심 파일
- `main.py` — exe 진입점, 탭 구조 (고정픽/보너스픽)
- `app.py` — 고정픽 GUI (tkinter), 모니터링 + 자동입력
- `bonus_pick.py` — 보너스픽 GUI, 예약 실행 (Selenium 유지)
- `src/api_controller.py` — **curl_cffi API 자동화 (고정픽 메인)**
- `src/browser_controller.py` — Selenium 자동화 (폴백/보너스픽용)
- `src/exceptions.py` — 공유 예외 클래스 (AutoCancelled, LoginFailed, InvalidParameter)
- `src/message_monitor.py` — 카카오톡 폴링 루프
- `version.py` — 버전 관리

## 기술 스택
- **API 자동화 (고정픽)**: curl_cffi + impersonate="chrome131" (Cloudflare TLS 우회)
- **브라우저 자동화 (보너스픽/폴백)**: undetected_chromedriver
- **프록시**: IPRoyal Rotating Residential ($1.75/GB, 2.1GB 잔여)
  - Host: geo.iproyal.com:12321
  - User: AtOwsaBFOqWr9Edk
  - Rotation: Randomize IP (요청마다 새 IP)
- **GUI**: tkinter (다크 테마, Neumorphism)
- **스레딩**: ThreadPoolExecutor (워커), queue.Queue (GUI 통신)

## API 엔드포인트
- **로그인**: POST `https://api.ddjea.com/api/app/user/login`
  - Body: `{"password": "...", "isValidator": true, "email": "..."}`
  - 헤더 대소문자 중요: `APP-VERSION`, `aws-check`, `set-aws`, `SET-LANGUAGE`
  - Origin, sec-ch-ua 헤더 필수
- **코드 제출**: POST `https://api.ddjea.com/api/app/second/share/user/follow/code`
  - Body: `{"code": "..."}`
  - APP-LOGIN-TOKEN 헤더에 토큰 포함

## 주요 설정값
- `STAGGER_DELAY`: API=0.3초, Selenium=10초 (자동 전환)
- 워커 최대: 30개 (Spinbox to=30)
- 코드 패턴: `^[A-Za-z0-9]{9}$` (9자리)

## 성능 비교
- Selenium: 119계정 / 워커4개 / ~20분
- **API (로그인 테스트)**: 119계정 / 워커1개 / **~7분 37초** (429 차단 0건)
- **API (첫 실전)**: 119계정 / 성공58 실패59 — "Frequent requests" 48건 (재시도 로직 추가로 해결 예정)

## 이전 프록시 실패 원인
- Sticky IP (30분 고정) + requests 라이브러리 TLS 핑거프린트 → Cloudflare 차단
- 해결: Randomize IP + curl_cffi (Chrome TLS 모방)

## 구현된 주요 기능
- 카카오톡 팝업 창 감지 → 클립보드 추출 → 코드 감지
- 다계정 API 자동입력 (curl_cffi, Chrome 불필요)
- **코드 제출 "Frequent requests" 재시도** (최대 6회, 3→6→9→12→15초 점진적 대기)
- 실패 계정 자동 재시도 (LoginFailed만)
- IPRoyal Rotating Residential 프록시
- **스케줄러 범위 기반 시작** (start~stop 범위 안이면 자동 재시작, 자동입력 중 대기)
- API/Selenium 자동 전환 (curl_cffi 없으면 Selenium 폴백)
- Selenium 백업: `dist/Selenium백업(v1.4)/픽보조_Selenium.exe`

## 보너스픽 흐름 (Selenium 유지)
1. 로그인 → 홈 이동 → Quickly buy coin
2. Invited me → Confirm to follow the order
3. Done/OK → Already followed the order 팝업 확인 → 완료

## 사용자 선호사항
- 커밋/푸시는 항상 사용자가 요청할 때만
- 빌드 후 dist/픽보조.exe 사용
- 워커 수: 상황에 따라 1~20개 조절
- 대화 중 중요한 내용은 항상 자동으로 memory에 저장 (별도 지시 불필요)
- **대화 종료 시 세션 기록 항상 자동 저장** (별도 요청 불필요)

## 세션 기록
- [2026-03-26](session_20260326.md) — ChromeDriver 146 고정, API/Selenium 빌드 분리, 대시보드 site_urls 동기화
- [2026-03-25](session_20260325.md) — API 안정화 (v1.5.6), 딜레이 조정, PC간 코드 일괄 전달 계획
- [2026-03-24](session_20260324.md) — config 자체저장 오인 버그 수정, API 99계정 테스트 준비
- [2026-03-23](session_20260323.md) — 코드 감지 후 재시작 방지, 수동 정지 재시작 방지, 대시보드 비밀번호 설정
- [2026-03-22](session_20260322.md) — 스케줄러 자정 넘김 버그 수정, 로그 축소, 대시보드 비밀번호 2개
- [2026-03-19 저녁](session_20260319c.md) — Railway 배포, 에이전트 commands.json 연동 수정, 멀티PC 운영 시작
- [2026-03-19 오후](session_20260319b.md) — 멀티PC 관리 시스템 (웹 대시보드 + 에이전트 + Railway 배포)
- [2026-03-19](session_20260319.md) — 스케줄러 자동시작 수정 (폴링 루프 try/finally)
- [2026-03-18](session_20260318.md) — Selenium 버전 수정, API 점검, 38계정 운영 계획

## 서버/배포 정보
- **Railway 도메인**: web-production-d682f.up.railway.app (.app이 정확, .com 아님)
- **대시보드 비밀번호**: ADMIN_PASSWORD + ADMIN_PASSWORD_2 환경변수 (2계정 지원)
- **볼륨**: /data (SQLite DB 영구 보존)
- **자동 배포**: GitHub main 브랜치 push 시 자동 재배포

## 피드백
- [정확한 답변 우선](feedback_accurate_answers.md) — 추측 금지, 모르면 확인 후 답변
- [빌드 및 배포 프로세스](feedback_build_process.md) — 코드 수정 시 양쪽 exe 빌드 + 배포 경로 복사까지 한 번에 완료
- [반복 실수 방지](feedback_no_repeat_mistakes.md) — 빌드 누락, 거짓 완료 보고, 근본 원인 미분석 방지 체크리스트
- [수정 전 확인 요청](feedback_ask_before_edit.md) — 코드 수정 전 항상 사용자에게 먼저 물어볼 것
- [Selenium 빌드 진입점](feedback_build_entry_point.md) — 빌드 시 반드시 main.py 사용 (app.py 아님)
- [작업내역 자동 저장](feedback_save_worklogs.md) — 매 대화 종료 시 작업내역/ 폴더에 텍스트 파일 자동 저장
- [배포 시 정보 표시](feedback_deploy_info.md) — 배포할 때 항상 URL, exe 파일명, 버전을 함께 보여줄 것
- [파일명 영문 사용](feedback_english_filenames.md) — 한글 파일명/폴더명 만들려고 하면 영문으로 만들라고 알려줄 것
