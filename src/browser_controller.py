"""
dsj44.com 주문 코드 자동 입력 모듈.

사전 조건:
  Chrome이 --remote-debugging-port=9222 옵션으로 실행 중이어야 함.

  실행 예시:
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
      --remote-debugging-port=9222
      --user-data-dir="C:\\chrome-debug"

자동화 흐름:
  1. https://dsj44.com/h5/#/login 접속
  2. 이메일 / 비밀번호 입력 후 로그인
  3. PC 버전으로 리다이렉트되면 h5 홈으로 강제 이동
  4. 'Quickly buy coin / Safe and Convenient' 클릭
  5. 'Invite me' 클릭
  6. 코드 입력 → confirm 클릭
"""
import logging
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("browser_controller")

# Chrome 설치 경로 후보 (일반적인 위치)
_CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
]

# 디버깅용 전용 프로필 경로 (실제 Chrome 프로필과 분리)
_DEBUG_PROFILE = str(Path.home() / "chrome-debug-profile")

LOGIN_URL = "https://dsj44.com/h5/#/login"
HOME_URL  = "https://dsj44.com/h5/#/home"
PC_HOST   = "dsj44.com/PC"

EMAIL    = "msdsgb@gmail.com"
PASSWORD = "qwer1234"

TIMEOUT = 15


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def find_chrome() -> str:
    """설치된 Chrome 경로 반환. 못 찾으면 RuntimeError."""
    for path in _CHROME_CANDIDATES:
        if path.exists():
            return str(path)
    raise RuntimeError(
        "Chrome을 찾을 수 없습니다.\n"
        "Chrome이 설치되어 있는지 확인하거나 직접 실행해 주세요."
    )


def launch_chrome(port: int = 9222, url: str = LOGIN_URL) -> None:
    """Chrome을 원격 디버깅 모드로 실행하고 지정 URL로 이동."""
    chrome = find_chrome()
    subprocess.Popen([
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={_DEBUG_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ])
    logger.info(f"Chrome 자동 실행 → {url}")


def _connect(port: int, login_url: str) -> webdriver.Chrome:
    """Chrome 연결. 실행 중이지 않으면 자동 실행 후 재시도."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception:
        logger.info("Chrome 미실행 감지 → 자동 실행")
        launch_chrome(port, login_url)
        time.sleep(4)
        return webdriver.Chrome(options=options)


def _js_click(driver, el) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", el)


def _click(driver, wait, xpath: str, label: str) -> None:
    """XPath 요소 클릭. 일반 클릭 실패 시 JS fallback."""
    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        try:
            el.click()
        except Exception:
            _js_click(driver, el)
        logger.info(f"클릭 성공: {label}")
    except TimeoutException:
        raise RuntimeError(f"요소를 찾을 수 없음: {label}")


def _ci(field: str) -> str:
    """XPath 대소문자 무시 비교용 translate() 구문."""
    U = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    L = "abcdefghijklmnopqrstuvwxyz"
    return f"translate({field},'{U}','{L}')"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def submit_order_code(code: str, port: int = 9222, login_url: str = LOGIN_URL) -> None:
    """
    지정 사이트에 로그인 후 9자리 코드 자동 입력.
    실패 시 RuntimeError raise.
    """
    logger.info(f"자동 입력 시작 | code={code}, port={port}, url={login_url}")
    driver = _connect(port, login_url)
    wait = WebDriverWait(driver, TIMEOUT)
    # ── Step 1: 로그인 페이지 접속 ────────────────────────────────
    logger.info("로그인 페이지 접속")
    driver.get(login_url)
    time.sleep(3)

    # ── Step 2: 노란색 Login 버튼 클릭 (class="login-btn") ───────
    try:
        el = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'login-btn')]")
        ))
        _js_click(driver, el)
        logger.info("클릭 성공: 노란색 Login 버튼")
    except TimeoutException:
        raise RuntimeError("요소를 찾을 수 없음: 노란색 Login 버튼")
    time.sleep(2)

    # ── Step 3: 아직 로그인 페이지면 이메일/비밀번호 입력 ────────────
    if "login" in driver.current_url.lower() or driver.current_url.rstrip("/") == login_url.rstrip("/"):
        logger.info("로그인 필요 → 이메일/비밀번호 입력")
        try:
            email_input = wait.until(EC.visibility_of_element_located((By.XPATH,
                "//input[contains(@placeholder,'email') or contains(@placeholder,'Email')]"
            )))
            pw_input = driver.find_element(By.XPATH,
                "//input[contains(@placeholder,'password') or contains(@placeholder,'Password')]"
            )

            # 이미 입력돼 있으면 그냥 Login 버튼만 클릭, 비어있으면 채우고 클릭
            if not email_input.get_attribute("value"):
                email_input.clear()
                email_input.send_keys(EMAIL)
                logger.info("이메일 입력 완료")
            else:
                logger.info("이메일 이미 입력됨, 생략")

            if not pw_input.get_attribute("value"):
                pw_input.clear()
                pw_input.send_keys(PASSWORD)
                logger.info("비밀번호 입력 완료")
            else:
                logger.info("비밀번호 이미 입력됨, 생략")

            # Login 버튼 클릭 (class="login-btn" div)
            login_btn = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'login-btn')]")
            ))
            _js_click(driver, login_btn)
            logger.info("Login 버튼 클릭, 이동 대기...")
            time.sleep(3)

        except TimeoutException:
            raise RuntimeError("로그인 입력창을 찾을 수 없음")
    else:
        logger.info("세션 유지됨 → 로그인 생략")

    # ── Step 4: PC 버전이면 h5 홈으로 강제 이동 ──────────────────
    if PC_HOST in driver.current_url or "#/home" not in driver.current_url:
        logger.info(f"현재 URL: {driver.current_url} → h5 홈으로 이동")
        driver.get(HOME_URL)
        time.sleep(3)

    logger.info(f"홈 접속 확인: {driver.current_url}")

    # ── Step 6: 'Quickly buy coin / Safe and Convenient' 클릭 ─────
    _click(driver, wait,
        xpath=(
            f"//*["
            f"  contains({_ci('text()')}, 'quickly buy')"
            f"  or contains({_ci('text()')}, 'safe and convenient')"
            f"]"
            f" | //*["
            f"  contains({_ci('text()')}, 'quickly buy')"
            f"  or contains({_ci('text()')}, 'safe and convenient')"
            f"]/ancestor::*[self::div or self::section or self::a][1]"
        ),
        label="Quickly buy coin 섹션",
    )
    time.sleep(1.5)

    # ── Step 7: 'Invite me' 클릭 ─────────────────────────────────
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(1)

    # ── Step 8: 코드 입력 ─────────────────────────────────────────
    try:
        inp = wait.until(EC.visibility_of_element_located((By.XPATH,
            f"//input["
            f"  contains({_ci('@placeholder')}, 'code')"
            f"  or contains({_ci('@placeholder')}, 'enter')"
            f"]"
        )))
        inp.clear()
        inp.send_keys(code)
        logger.info(f"코드 입력 완료: {code}")
        time.sleep(0.3)
    except TimeoutException:
        raise RuntimeError("코드 입력창을 찾을 수 없음")

    # ── Step 9: confirm 클릭 ──────────────────────────────────────
    _click(driver, wait,
        xpath=(
            f"//*["
            f"  contains({_ci('text()')}, 'confirm')"
            f"  or contains({_ci('text()')}, 'cunfim')"
            f"]"
        ),
        label="confirm 버튼",
    )
    logger.info("자동 입력 완료!")
