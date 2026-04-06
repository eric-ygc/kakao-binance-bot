---
name: 반복 실수 방지 체크리스트
description: 코드 수정 시 반드시 지켜야 할 검증 절차 — 빌드 누락, 거짓 완료 보고, 근본 원인 미분석 방지
type: feedback
---

## 절대 반복하지 말 것

1. **코드 수정 후 exe 빌드 누락 금지** — 수정했으면 반드시 양쪽(API + Selenium) 빌드 + 배포 경로 복사까지 완료
2. **안 한 작업을 "완료"라고 기록 금지** — 세션 기록에 쓰기 전에 실제 파일 존재/타임스탬프 검증
3. **이미 아는 정보를 다시 물어보지 말 것** — 빌드 명령, 배포 경로 등은 메모리 확인 후 바로 실행
4. **표면적 수정(try/finally 등)만 하고 근본 원인을 놓치지 말 것** — 보너스픽은 되고 고정픽은 안 되면, 두 코드의 구조 차이를 먼저 비교

**Why:** 사용자가 같은 문제로 3번 이상 수정 요청함. 코드 수정 → 빌드 누락 → 구버전 exe 실행 → 또 안 됨 → 또 수정 요청의 악순환. 세션 기록에 거짓 완료 보고까지 해서 신뢰 깨짐.

**How to apply:**
- 코드 수정 완료 후 체크리스트:
  ☐ API exe 빌드 (`pyinstaller --onefile --windowed --collect-all curl_cffi --name 픽보조 main.py`)
  ☐ Selenium exe 빌드 (`cd .selenium-build && rm -rf build dist && pyinstaller --onefile --windowed --name 픽보조_Selenium main.py`)
  ☐ Selenium exe 복사 (`.selenium-build/dist/픽보조_Selenium.exe` → `dist/Selenium백업(v1.4)/픽보조_Selenium.exe`)
  ☐ `ls -la`로 양쪽 exe 타임스탬프 확인
  ☐ 세션 기록 작성 시 실제 완료 여부 재확인
- 버그 수정 시: 동작하는 코드(보너스픽)와 안 되는 코드(고정픽)의 **구조적 차이**를 먼저 비교
