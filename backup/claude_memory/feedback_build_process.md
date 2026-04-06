---
name: 빌드 및 배포 프로세스
description: 코드 수정 후 반드시 양쪽 exe 빌드 + 배포 경로 복사까지 완료해야 함
type: feedback
---

코드 수정 시 반드시 API + Selenium 양쪽 exe 빌드 및 배포까지 한 번에 완료할 것.

**빌드 명령:**
- API: `cd 프로젝트루트 && pyinstaller --onefile --windowed --collect-all curl_cffi --name 픽보조 main.py`
- Selenium: `cd .selenium-build && rm -rf build dist && pyinstaller --onefile --windowed --name 픽보조_Selenium main.py`

**배포 경로:**
- API exe: `dist/픽보조.exe` (빌드 시 자동 배치)
- Selenium exe: `.selenium-build/dist/픽보조_Selenium.exe` → `dist/Selenium백업(v1.4)/픽보조_Selenium.exe`로 복사

**Why:** 코드만 수정하고 exe 빌드를 빠뜨려서 수정이 반영 안 된 채로 사용자가 실행함. 빌드 명령이나 복사 경로를 다시 물어봐서 사용자 불편 초래.

**How to apply:** 코드 수정 완료 → 빌드 명령 질문 없이 바로 실행 → 배포 경로 복사 → ls로 exe 파일 존재/크기 검증 → 완료 보고. 물어보지 말고 바로 할 것. 세션 기록에 "완료"라고 쓰기 전에 반드시 실제 확인.
