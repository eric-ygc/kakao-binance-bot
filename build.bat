@echo off
chcp 65001 >nul
echo ============================================
echo   픽보조 빌드 스크립트
echo ============================================
echo.
echo   [1] API 버전만 빌드
echo   [2] Selenium 버전만 빌드
echo   [3] 양쪽 다 빌드
echo   [4] 취소
echo.
set /p choice="선택: "

if "%choice%"=="1" goto BUILD_API
if "%choice%"=="2" goto BUILD_SELENIUM
if "%choice%"=="3" goto BUILD_BOTH
if "%choice%"=="4" goto END
echo 잘못된 입력입니다.
goto END

:BUILD_API
echo.
echo ── API 버전 빌드 중... ──
pyinstaller --onefile --windowed --collect-all curl_cffi --name 픽보조 main.py
if errorlevel 1 (
    echo ✗ API 빌드 실패!
    goto END
)
echo ✓ API 빌드 완료: dist\픽보조.exe
goto END

:BUILD_SELENIUM
echo.
echo ── Selenium 버전 빌드 중... ──
pyinstaller --onefile --windowed --name 픽보조_Selenium main.py
if errorlevel 1 (
    echo ✗ Selenium 빌드 실패!
    goto END
)
copy /Y "dist\픽보조_Selenium.exe" "dist\Selenium백업(v1.4)\픽보조_Selenium.exe"
del "dist\픽보조_Selenium.exe"
echo ✓ Selenium 빌드 완료: dist\Selenium백업(v1.4)\픽보조_Selenium.exe
goto END

:BUILD_BOTH
echo.
echo ── API 버전 빌드 중... ──
pyinstaller --onefile --windowed --collect-all curl_cffi --name 픽보조 main.py
if errorlevel 1 (
    echo ✗ API 빌드 실패!
    goto END
)
echo ✓ API 빌드 완료: dist\픽보조.exe
echo.
echo ── Selenium 버전 빌드 중... ──
pyinstaller --onefile --windowed --name 픽보조_Selenium main.py
if errorlevel 1 (
    echo ✗ Selenium 빌드 실패!
    goto END
)
copy /Y "dist\픽보조_Selenium.exe" "dist\Selenium백업(v1.4)\픽보조_Selenium.exe"
del "dist\픽보조_Selenium.exe"
echo ✓ Selenium 빌드 완료: dist\Selenium백업(v1.4)\픽보조_Selenium.exe
echo.
echo ✓ 양쪽 빌드 완료!
goto END

:END
echo.
pause
