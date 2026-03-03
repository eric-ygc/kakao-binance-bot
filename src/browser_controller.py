"""
dsj44.com 주문 코드 자동 입력 모듈.

자동화 흐름:
  1. https://dsj44.com/h5/#/login 접속
  2. 이메일 / 비밀번호 입력 후 로그인
  3. PC 버전으로 리다이렉트되면 h5 홈으로 강제 이동
  4. 'Quickly buy coin / Safe and Convenient' 클릭
  5. 'Invite me' 클릭
  6. 코드 입력 → confirm 클릭
"""
import logging
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("browser_controller")

LOGIN_URL = "https://dsj44.com/h5/#/login"
HOME_URL  = "https://dsj44.com/h5/#/home"
PC_HOST   = "dsj44.com/PC"

EMAIL    = "msdsgb@gmail.com"
PASSWORD = "qwer1234"

TIMEOUT = 15


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

class AutoCancelled(Exception):
    """중지 버튼으로 자동 입력이 취소됐을 때 발생."""


def _open_driver(status_cb=None) -> webdriver.Chrome:
    """Selenium으로 Chrome을 직접 실행하고 WebDriver 반환."""
    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    _st("Chrome 실행 중...")
    options = webdriver.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-extensions")
    driver = webdriver.Chrome(options=options)
    _st("Chrome 실행 완료")
    return driver


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

def _do_submit(driver, code: str, login_url: str, _st) -> None:
    """단일 사이트에서 코드 입력 전체 흐름."""
    wait = WebDriverWait(driver, TIMEOUT)

    # ── Step 1: 로그인 페이지 접속 ────────────────────────────────
    _st("로그인 페이지 접속 중...")
    driver.get(login_url)
    time.sleep(5)

    # ── Step 2: 노란색 Login 버튼 클릭 ───────────────────────────
    _st("Login 버튼 클릭 중...")
    try:
        el = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'login-btn')]")
        ))
        _js_click(driver, el)
    except TimeoutException:
        raise RuntimeError("요소를 찾을 수 없음: 노란색 Login 버튼")
    time.sleep(3)

    # ── Step 3: 로그인 필요 시 이메일/비밀번호 입력 ───────────────
    if "login" in driver.current_url.lower() or \
            driver.current_url.rstrip("/") == login_url.rstrip("/"):
        _st("로그인 필요 → 이메일/비밀번호 입력 중...")
        try:
            email_input = wait.until(EC.visibility_of_element_located((By.XPATH,
                "//input[contains(@placeholder,'email') or contains(@placeholder,'Email')]"
            )))
            pw_input = driver.find_element(By.XPATH,
                "//input[contains(@placeholder,'password') or contains(@placeholder,'Password')]"
            )
            if not email_input.get_attribute("value"):
                email_input.clear()
                email_input.send_keys(EMAIL)
            if not pw_input.get_attribute("value"):
                pw_input.clear()
                pw_input.send_keys(PASSWORD)
            login_btn = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'login-btn')]")
            ))
            _js_click(driver, login_btn)
            _st("로그인 완료, 이동 대기...")
            time.sleep(5)
        except TimeoutException:
            raise RuntimeError("로그인 입력창을 찾을 수 없음")
    else:
        _st("세션 유지됨 → 로그인 생략")

    # ── Step 4: PC 버전이면 h5 홈으로 이동 ──────────────────────
    if PC_HOST in driver.current_url or "#/home" not in driver.current_url:
        _st("h5 홈으로 이동 중...")
        driver.get(HOME_URL)
        time.sleep(4)
    _st("홈 접속 완료")

    # ── Step 5: Quickly buy coin 클릭 ────────────────────────────
    _st("Quickly buy coin 클릭 중...")
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
    time.sleep(2)

    # ── Step 6: Invited me 클릭 ──────────────────────────────────
    _st("Invited me 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(2)

    # ── Step 7: 코드 입력 ────────────────────────────────────────
    _st(f"코드 입력 중: {code}")
    try:
        inp = wait.until(EC.visibility_of_element_located((By.XPATH,
            f"//input["
            f"  contains({_ci('@placeholder')}, 'code')"
            f"  or contains({_ci('@placeholder')}, 'enter')"
            f"]"
        )))
        inp.clear()
        inp.send_keys(code)
        time.sleep(1)
    except TimeoutException:
        raise RuntimeError("코드 입력창을 찾을 수 없음")

    # ── Step 8: confirm 클릭 ─────────────────────────────────────
    _st("Confirm 버튼 클릭 중...")
    _click(driver, wait,
        xpath=(
            f"//*["
            f"  contains({_ci('text()')}, 'confirm')"
            f"  or contains({_ci('text()')}, 'cunfim')"
            f"]"
        ),
        label="confirm 버튼",
    )
    _st("Confirm 완료 — 결과 확인 중...")
    time.sleep(3)


def submit_order_code(
    code: str,
    port: int = 9222,           # 하위 호환용, 현재 미사용
    login_url=LOGIN_URL,        # str 또는 list[str]
    status_cb=None,
    cancel_event=None,
) -> None:
    """
    지정 사이트에 로그인 후 9자리 코드 자동 입력.
    login_url이 리스트인 경우 실패 시 다음 URL로 순서대로 시도.
    """
    if cancel_event and cancel_event.is_set():
        raise AutoCancelled()

    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    # 리스트 정규화
    if isinstance(login_url, str):
        urls = [login_url] if login_url.strip() else [LOGIN_URL]
    else:
        urls = [u.strip() for u in login_url if u.strip()]
    if not urls:
        urls = [LOGIN_URL]

    _st(f"자동 입력 시작 | code={code} | 사이트 {len(urls)}개")

    last_error = None
    for idx, url in enumerate(urls):
        if len(urls) > 1:
            _st(f"[{idx+1}/{len(urls)}] {url}")
        driver = _open_driver(status_cb)
        try:
            _do_submit(driver, code, url, _st)
            _st("자동 입력 완료!")
            return  # 성공
        except Exception as e:
            last_error = e
            _st(f"✗ 사이트 {idx+1} 실패: {e}")
        finally:
            try:
                driver.quit()
                logger.info("Chrome 종료")
            except Exception:
                pass
        if idx < len(urls) - 1:
            _st("다음 사이트로 재시도...")

    raise RuntimeError(f"모든 사이트({len(urls)}개) 실패: {last_error}")
