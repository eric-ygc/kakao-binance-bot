---
name: Selenium 빌드 진입점
description: Selenium 버전 빌드 시 반드시 main.py로 빌드할 것 (app.py 아님)
type: feedback
---

Selenium 버전 빌드 시 진입점은 반드시 **main.py**여야 한다. app.py로 빌드하면 검은 창만 뜬다.

**Why:** app.py는 main.py의 탭 구조 안에서 임베드되어 실행되는 구조. 단독 실행 시 GUI가 제대로 렌더링 안 됨.
**How to apply:** `.selenium-build/` 빌드 명령: `python -m PyInstaller --onefile --windowed --name 픽보조_Selenium main.py`
