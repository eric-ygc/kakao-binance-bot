"""
dsj44.com 자동화 모듈.

흐름 A — 주문 코드 입력 (submit_order_code):
  1. 로그인  2. 홈 이동  3. Quickly buy coin  4. Invited me
  5. 코드 입력  6. Confirm  7. 결과 확인

흐름 B — No more 클릭 (click_no_more):
  1. 로그인  2. 홈 이동  3. Quickly buy coin  4. Invited me
  5. No more 클릭  6. Done/OK 클릭
"""
import logging
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("browser_controller")

LOGIN_URL = "https://dsj44.com/h5/#/login"
HOME_URL  = "https://dsj44.com/h5/#/home"
PC_HOST   = "dsj44.com/PC"

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
    time.sleep(0.1)
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


def _do_login(driver, wait, login_url: str, email: str, password: str, _st) -> None:
    """
    로그인 URL 접속 → 이메일/비밀번호 바로 입력 → 로그인 버튼 클릭 → URL 전환 대기.
    이미 세션이 유지된 경우(홈으로 리다이렉트) 로그인 단계를 생략한다.
    """
    _st("로그인 페이지 접속 중...")
    driver.get(login_url)

    # 이메일 입력창 대기 — 세션 유지 시 홈으로 리다이렉트되므로 TimeoutException 발생
    try:
        email_input = wait.until(EC.visibility_of_element_located((By.XPATH,
            "//input[contains(@placeholder,'email') or contains(@placeholder,'Email')]"
        )))
    except TimeoutException:
        _st("세션 유지됨 → 로그인 생략")
        return

    _st(f"로그인 중: {email}")
    try:
        pw_input = wait.until(EC.visibility_of_element_located((By.XPATH,
            "//input[contains(@placeholder,'password') or contains(@placeholder,'Password')]"
        )))
    except TimeoutException:
        raise RuntimeError("비밀번호 입력창을 찾을 수 없음")

    email_input.clear()
    email_input.send_keys(email)
    pw_input.clear()
    pw_input.send_keys(password)
    time.sleep(0.2)  # 입력 안정화
    pw_input.send_keys(Keys.RETURN)   # 버튼 클릭 없이 Enter로 제출
    _st("로그인 완료, 페이지 전환 대기...")

    # 로그인 후 URL이 login에서 벗어날 때까지 대기
    try:
        wait.until(lambda d: "login" not in d.current_url.lower())
    except TimeoutException:
        raise RuntimeError("로그인 후 페이지 전환 실패 — 이메일/비밀번호 확인 요망")


def _go_home(driver, wait, _st) -> None:
    """현재 URL이 h5 홈이 아닌 경우 홈으로 이동 후 핵심 요소 대기."""
    if PC_HOST in driver.current_url or "#/home" not in driver.current_url:
        _st("h5 홈으로 이동 중...")
        driver.get(HOME_URL)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH,
                f"//*[contains({_ci('text()')}, 'quickly buy')"
                f" or contains({_ci('text()')}, 'safe and convenient')]"
            )))
        except TimeoutException:
            pass  # 요소 미감지 시에도 계속 진행
    _st("홈 접속 완료")


def _check_submit_result(driver, _st, timeout: float = 5.0) -> None:
    """
    Confirm 클릭 후 결과 메시지를 폴링하여 성공/실패를 판별한다.
    에러 키워드가 감지되면 RuntimeError 발생.
    타임아웃까지 에러 미감지 시 성공으로 간주.
    """
    ERROR_KEYWORDS = [
        "fail", "error", "invalid", "already", "incorrect", "wrong",
        "expired", "not found", "unsuccessful", "denied", "exist",
        "used", "repeat", "duplicate",
    ]
    SUCCESS_KEYWORDS = [
        "success", "complete", "done", "submitted", "received", "ok",
    ]

    CONTAINER_XPATH = (
        "//*["
        "  contains(@class,'toast') or contains(@class,'alert') or"
        "  contains(@class,'tip') or contains(@class,'notice') or"
        "  contains(@class,'snack') or contains(@class,'msg') or"
        "  contains(@class,'popup') or contains(@class,'result') or"
        "  contains(@class,'modal-body') or contains(@class,'van-toast') or"
        "  contains(@class,'van-dialog') or contains(@class,'van-notify')"
        "]"
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            elements = driver.find_elements(By.XPATH, CONTAINER_XPATH)
            for el in elements:
                try:
                    if not el.is_displayed():
                        continue
                    text = el.text.strip()
                    if not text:
                        continue
                    text_lower = text.lower()
                    for kw in ERROR_KEYWORDS:
                        if kw in text_lower:
                            raise RuntimeError(f"제출 실패 — 사이트 응답: {text}")
                    for kw in SUCCESS_KEYWORDS:
                        if kw in text_lower:
                            _st(f"성공 확인: {text}")
                            return
                except RuntimeError:
                    raise
                except Exception:
                    pass
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(0.3)

    _st("결과 메시지 미감지 → 성공으로 간주")


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def _do_submit(driver, code: str, login_url: str, email: str, password: str, _st) -> None:
    """단일 사이트에서 코드 입력 전체 흐름."""
    wait = WebDriverWait(driver, TIMEOUT)

    # ── Step 1: 로그인 ────────────────────────────────────────────
    _do_login(driver, wait, login_url, email, password, _st)

    # ── Step 2: 홈 이동 ──────────────────────────────────────────
    _go_home(driver, wait, _st)

    # ── Step 3: Quickly buy coin 클릭 ────────────────────────────
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
    time.sleep(1.5)

    # ── Step 4: Invited me 클릭 ──────────────────────────────────
    _st("Invited me 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(1.5)

    # ── Step 5: 코드 입력 ────────────────────────────────────────
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
        time.sleep(0.5)
    except TimeoutException:
        raise RuntimeError("코드 입력창을 찾을 수 없음")

    # ── Step 6: confirm 클릭 ─────────────────────────────────────
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
    time.sleep(1.5)

    # ── Step 7: 결과 확인 ────────────────────────────────────────
    _st("결과 확인 중...")
    _check_submit_result(driver, _st, timeout=5.0)


def submit_order_code(
    code: str,
    port: int = 9222,           # 하위 호환용, 현재 미사용
    login_url=LOGIN_URL,        # str 또는 list[str]
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
) -> None:
    """
    지정 사이트에 로그인 후 코드 자동 입력.
    login_url이 리스트인 경우 실패 시 다음 URL로 순서대로 시도.
    """
    if cancel_event and cancel_event.is_set():
        raise AutoCancelled()

    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    if isinstance(login_url, str):
        urls = [login_url] if login_url.strip() else [LOGIN_URL]
    else:
        urls = [u.strip() for u in login_url if u.strip()]
    if not urls:
        urls = [LOGIN_URL]

    _st(f"자동 입력 시작 | code={code} | 계정={email} | 사이트 {len(urls)}개")

    last_error = None
    for idx, url in enumerate(urls):
        if len(urls) > 1:
            _st(f"[{idx+1}/{len(urls)}] {url}")
        driver = _open_driver(status_cb)
        try:
            _do_submit(driver, code, url, email, password, _st)
            _st("자동 입력 완료!")
            return
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


def _do_no_more(driver, login_url: str, email: str, password: str, _st) -> None:
    """No more → Done/OK 흐름 단일 사이트 실행."""
    wait = WebDriverWait(driver, TIMEOUT)

    # ── Step 1: 로그인 ────────────────────────────────────────────
    _do_login(driver, wait, login_url, email, password, _st)

    # ── Step 2: 홈 이동 ──────────────────────────────────────────
    _go_home(driver, wait, _st)

    # ── Step 3: Quickly buy coin 클릭 ────────────────────────────
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
    time.sleep(1.5)

    # ── Step 4: Invited me 클릭 ──────────────────────────────────
    _st("Invited me 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(1.5)

    # ── Step 5: No more 클릭 ─────────────────────────────────────
    _st("No more 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'no more')]",
        label="No more",
    )
    time.sleep(1.5)

    # ── Step 6: Done / OK 클릭 ───────────────────────────────────
    _st("Done/OK 클릭 중...")
    _click(driver, wait,
        xpath=(
            f"//*["
            f"  contains({_ci('text()')}, 'done')"
            f"  or contains({_ci('text()')}, 'ok')"
            f"]"
        ),
        label="Done/OK 버튼",
    )
    time.sleep(1.0)
    _st("완료!")


def click_no_more(
    port: int = 9222,           # 하위 호환용, 현재 미사용
    login_url=LOGIN_URL,        # str 또는 list[str]
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
) -> None:
    """
    No more → Done/OK 흐름 실행.
    login_url이 리스트인 경우 실패 시 다음 URL로 순서대로 시도.
    """
    if cancel_event and cancel_event.is_set():
        raise AutoCancelled()

    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    if isinstance(login_url, str):
        urls = [login_url] if login_url.strip() else [LOGIN_URL]
    else:
        urls = [u.strip() for u in login_url if u.strip()]
    if not urls:
        urls = [LOGIN_URL]

    _st(f"No more 실행 시작 | 계정={email} | 사이트 {len(urls)}개")

    last_error = None
    for idx, url in enumerate(urls):
        if len(urls) > 1:
            _st(f"[{idx+1}/{len(urls)}] {url}")
        driver = _open_driver(status_cb)
        try:
            _do_no_more(driver, url, email, password, _st)
            _st("No more 완료!")
            return
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
