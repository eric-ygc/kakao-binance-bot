"""
dsj44.com 자동화 모듈.

흐름 A — 주문 코드 입력 (submit_order_code):
  1. 로그인  2. 홈 이동  3. Quickly buy coin  4. Invited me
  5. 코드 입력  6. Confirm

흐름 B — No more 클릭 (click_no_more):
  1. 로그인  2. 홈 이동  3. Quickly buy coin  4. Invited me
  5. No more 클릭  6. Done/OK 클릭
"""
import logging
import os
import tempfile
import time
import zipfile

import undetected_chromedriver as uc
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
# 예외 클래스 (공유 모듈에서 import)
# ---------------------------------------------------------------------------

from src.exceptions import AutoCancelled, LoginFailed, InvalidParameter


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _make_proxy_auth_ext(host: str, port: str, user: str, pwd: str) -> str:
    """인증 프록시용 Chrome 확장(.zip)을 임시 파일로 생성하고 경로 반환."""
    manifest = (
        '{"version":"1.0.0","manifest_version":2,"name":"ProxyAuth",'
        '"permissions":["proxy","tabs","unlimitedStorage","storage",'
        '"<all_urls>","webRequest","webRequestBlocking"],'
        '"background":{"scripts":["bg.js"]},'
        '"minimum_chrome_version":"22.0.0"}'
    )
    bg = f"""
var cfg={{mode:"fixed_servers",rules:{{singleProxy:{{scheme:"http",host:"{host}",port:parseInt("{port}")}},bypassList:["localhost"]}}}};
chrome.proxy.settings.set({{value:cfg,scope:"regular"}},function(){{}});
chrome.webRequest.onAuthRequired.addListener(
  function(){{return{{authCredentials:{{username:"{user}",password:"{pwd}"}}}}}},
  {{urls:["<all_urls>"]}},["blocking"]);
"""
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", manifest)
        zf.writestr("bg.js", bg)
    return path


def _chk(cancel_event) -> None:
    """cancel_event 가 set 되어 있으면 AutoCancelled 발생."""
    if cancel_event and cancel_event.is_set():
        raise AutoCancelled()


_driver_count = 0  # 창 위치 오프셋용 카운터

def _open_driver(status_cb=None, proxy: str = "") -> uc.Chrome:
    """undetected-chromedriver로 Chrome을 실행하고 WebDriver 반환 (봇 감지 우회)."""
    global _driver_count

    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    _st("Chrome 실행 중...")
    options = uc.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-popup-blocking")

    proxy_parts = [p.strip() for p in proxy.split(":")] if proxy else []
    if len(proxy_parts) == 4:
        # host:port:user:pass — 인증 프록시 (Chrome 확장으로 처리)
        host, port, user, pwd = proxy_parts
        ext_path = _make_proxy_auth_ext(host, port, user, pwd)
        options.add_extension(ext_path)
        _st(f"프록시 적용 (인증): {host}:{port}")
    elif len(proxy_parts) == 2:
        # host:port — 인증 없는 프록시
        options.add_argument(f"--proxy-server={proxy}")
        _st(f"프록시 적용: {proxy}")

    driver = uc.Chrome(options=options)
    # h5 모바일 레이아웃으로 렌더링 (로그인 버튼 등이 화면 안에 표시됨)
    driver.set_window_size(480, 1020)
    # 창 겹침 방지: 가로 4열 배치
    col = _driver_count % 4
    driver.set_window_position(col * 480, 0)
    _driver_count += 1
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


_EMAIL_XPATH = (
    "//input[@type='email'"
    " or contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')"
    " or contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'이메일')"
    " or contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]"
)
_PW_XPATH = (
    "//input[@type='password'"
    " or contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'password')"
    " or contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'비밀번호')]"
)

_LOGIN_BTN_XPATH = (
    "//button["
    f"  contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')"
    f"  or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in')"
    f"  or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign in')"
    f"  or contains(text(),'로그인')"
    f"  or @type='submit'"
    "]"
    " | //div["
    f"  contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')"
    f"  or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in')"
    f"  or contains(text(),'로그인')"
    "]"
    " | //span["
    f"  contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')"
    f"  or contains(text(),'로그인')"
    "]"
)


def _do_login(driver, wait, login_url: str, email: str, password: str, _st,
              cancel_event=None) -> None:
    """
    로그인 URL 접속 → 이메일/비밀번호 입력 → 로그인 버튼 클릭.
    세션이 이미 유지된 경우 로그인 단계를 생략한다.

    로그인 실패(잘못된 비밀번호 등) 시 LoginFailed 발생.
    """
    _chk(cancel_event)
    _st("로그인 페이지 접속 중...")
    driver.get(login_url)
    time.sleep(1)  # 초기 리다이렉트 대기

    # 세션 유지 여부를 URL로 먼저 판단
    if "login" not in driver.current_url.lower():
        _st("세션 유지됨 → 로그인 생략")
        return

    _chk(cancel_event)

    # 이메일 입력창 탐색
    try:
        email_input = wait.until(EC.visibility_of_element_located((By.XPATH, _EMAIL_XPATH)))
    except TimeoutException:
        raise RuntimeError("이메일 입력창을 찾을 수 없음 (로그인 페이지 구조 확인 필요)")

    try:
        pw_input = wait.until(EC.visibility_of_element_located((By.XPATH, _PW_XPATH)))
    except TimeoutException:
        raise RuntimeError("비밀번호 입력창을 찾을 수 없음")

    _chk(cancel_event)
    _st(f"로그인 중: {email}")
    email_input.clear()
    email_input.send_keys(email)
    pw_input.clear()
    pw_input.send_keys(password)
    time.sleep(0.3)

    _chk(cancel_event)

    # 로그인 버튼 클릭 — JavaScript DOM 탐색으로 버튼 클릭
    time.sleep(0.5)  # 버튼 렌더링 대기
    clicked = driver.execute_script("""
        function isVisible(el) {
            var r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }
        // 1순위: class 에 'login-btn' / 'loginBtn' / 'login_btn' 포함
        var byClass = document.querySelectorAll(
            '[class*="login-btn"], [class*="loginBtn"], [class*="login_btn"]'
        );
        for (var i = 0; i < byClass.length; i++) {
            if (isVisible(byClass[i])) {
                byClass[i].click();
                return byClass[i].className;
            }
        }
        // 2순위: button[type=submit] 또는 input[type=submit]
        var submits = document.querySelectorAll('button[type="submit"], input[type="submit"]');
        for (var i = 0; i < submits.length; i++) {
            if (isVisible(submits[i])) {
                submits[i].click();
                return submits[i].textContent.trim() || 'submit';
            }
        }
        // 3순위: 텍스트가 정확히 'login' 또는 '로그인' 인 요소 (title/header 클래스 제외)
        var keywords = ['login', '로그인', 'log in', 'sign in'];
        var candidates = document.querySelectorAll('button, [role="button"], div, span, a');
        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            if (!isVisible(el)) continue;
            var cls = (el.className || '').toString().toLowerCase();
            if (cls.includes('title') || cls.includes('header') || cls.includes('download') || cls.includes('back')) continue;
            if (el.querySelector('input') || el.querySelector('button')) continue;
            var text = (el.textContent || '').trim().toLowerCase();
            if (keywords.some(function(k){ return text === k; })) {
                el.click();
                return el.textContent.trim();
            }
        }
        return null;
    """)

    if clicked:
        _st(f"로그인 버튼 클릭 완료: '{clicked}'")
    else:
        # 폴백: form.submit()
        try:
            driver.execute_script("document.querySelector('form').submit();")
            _st("form.submit() 폴백 실행")
            clicked = True
        except Exception:
            pw_input.send_keys(Keys.RETURN)
            _st("Enter 폴백 실행")

    # ── 로그인 결과 폴링 ──────────────────────────────────────────
    # URL에 'login'이 사라지면 성공, 3초 후에도 'login' 페이지에 머물면 실패.
    _st("로그인 결과 확인 중...")
    for attempt in range(80):  # 0.3s × 80 = 최대 24초
        _chk(cancel_event)
        time.sleep(0.3)
        current = driver.current_url.lower()

        if "login" not in current:
            _st("로그인 성공 — URL 전환 확인")
            return

        # 20초(attempt=66) 이후에도 로그인 페이지 잔류 → 비밀번호 오류로 판단
        if attempt >= 66:
            raise LoginFailed(
                f"로그인 실패 — 20초 후에도 로그인 페이지 잔류 ({email})"
            )

    # 루프 정상 종료(이론상 도달 불가)
    raise LoginFailed(f"로그인 실패 — 타임아웃 ({email})")


def _go_home(driver, wait, _st, cancel_event=None) -> None:
    """현재 URL이 h5 홈이 아닌 경우에만 홈으로 이동.
    이미 #/home 이면 건너뜀(미러 사이트 도메인 유지).
    홈 이동 후 login 페이지로 리다이렉트되면 LoginFailed."""
    _chk(cancel_event)
    # 이미 #/home 에 있으면 네비게이션 생략 — 미러사이트(dexvip.shop 등) 도메인 보존
    if PC_HOST in driver.current_url or "#/home" not in driver.current_url:
        _st("h5 홈으로 이동 중...")
        driver.get(HOME_URL)
        time.sleep(1)
        # 홈 이동 후 로그인 페이지로 튕긴 경우 → 세션 만료
        if "login" in driver.current_url.lower():
            raise LoginFailed("홈 이동 후 로그인 페이지로 리다이렉트 — 세션 만료")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH,
                f"//*[contains({_ci('text()')}, 'quickly buy')"
                f" or contains({_ci('text()')}, 'safe and convenient')]"
            )))
        except TimeoutException:
            pass  # 요소 미감지 시에도 계속 진행
    _st("홈 접속 완료")


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def _do_submit(driver, code: str, login_url: str, email: str, password: str, _st,
               cancel_event=None) -> None:
    """단일 사이트에서 코드 입력 전체 흐름."""
    wait = WebDriverWait(driver, TIMEOUT)

    # ── Step 1: 로그인 ────────────────────────────────────────────
    _do_login(driver, wait, login_url, email, password, _st, cancel_event)

    # ── Step 2: 홈 이동 ──────────────────────────────────────────
    _go_home(driver, wait, _st, cancel_event)

    # ── Step 3: Quickly buy coin 클릭 ────────────────────────────
    _chk(cancel_event)
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
    _chk(cancel_event)
    _st("Invited me 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(1.5)

    # ── Step 5: 코드 입력 ────────────────────────────────────────
    _chk(cancel_event)
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

    # ── Step 6: Confirm 클릭 ─────────────────────────────────────
    _chk(cancel_event)
    _st("Confirm 버튼 클릭 중...")
    _click(driver, wait,
        xpath=(
            f"//*["
            f"  contains({_ci('text()')}, 'confirm')"
            f"  or contains({_ci('text()')}, 'cunfim')"
            f"  or contains({_ci('text()')}, 'submit')"
            f"  or contains({_ci('text()')}, 'ok')"
            f"  or contains({_ci('text()')}, '확인')"
            f"  or contains({_ci('text()')}, 'send')"
            f"]"
        ),
        label="confirm 버튼",
    )
    time.sleep(0.8)

    # ── Step 7: 결과 팝업 감지 (Success / Invalid parameter) ─────
    _st("결과 확인 중...")
    deadline = time.time() + 2
    while time.time() < deadline:
        _chk(cancel_event)
        try:
            els = driver.find_elements(By.XPATH,
                f"//*[contains({_ci('text()')}, 'success')]"
            )
            if els:
                _st("✓ Success 팝업 확인")
                return
        except Exception:
            pass
        try:
            els = driver.find_elements(By.XPATH,
                f"//*[contains({_ci('text()')}, 'invalid parameter')"
                f"  or contains({_ci('text()')}, 'invalid param')]"
            )
            if els:
                raise InvalidParameter("❌ Invalid parameter — 코드 제출 실패")
        except InvalidParameter:
            raise
        except Exception:
            pass
        time.sleep(0.3)
    _st("팝업 미감지 — 성공으로 간주")


def submit_order_code(
    code: str,
    port: int = 9222,           # 하위 호환용, 현재 미사용
    login_url=LOGIN_URL,        # str 또는 list[str]
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
    proxy: str = "",
) -> None:
    """
    지정 사이트에 로그인 후 코드 자동 입력.
    login_url이 리스트인 경우 실패 시 다음 URL로 순서대로 시도.
    LoginFailed 발생 시 다음 사이트 시도 없이 즉시 예외 전파.
    """
    _chk(cancel_event)

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
        _chk(cancel_event)
        if len(urls) > 1:
            _st(f"[{idx+1}/{len(urls)}] {url}")
        driver = _open_driver(status_cb, proxy=proxy)
        try:
            _do_submit(driver, code, url, email, password, _st, cancel_event)
            _st("자동 입력 완료!")
            return
        except AutoCancelled:
            raise
        except LoginFailed:
            raise
        except InvalidParameter:
            raise
        except Exception as e:
            last_error = e
            _st(f"✗ 사이트 {idx+1} 실패: [{type(e).__name__}] {e}")
        finally:
            try:
                driver.quit()
                logger.info("Chrome 종료")
            except Exception:
                pass
        if idx < len(urls) - 1:
            _st("다음 사이트로 재시도...")

    raise RuntimeError(f"모든 사이트({len(urls)}개) 실패: {last_error}")


def _do_no_more(driver, login_url: str, email: str, password: str, _st,
                cancel_event=None) -> None:
    """No more → Done/OK 흐름 단일 사이트 실행."""
    wait = WebDriverWait(driver, TIMEOUT)

    # ── Step 1: 로그인 ────────────────────────────────────────────
    _do_login(driver, wait, login_url, email, password, _st, cancel_event)

    # ── Step 2: 홈 이동 ──────────────────────────────────────────
    _go_home(driver, wait, _st, cancel_event)

    # ── Step 3: Quickly buy coin 클릭 ────────────────────────────
    _chk(cancel_event)
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
    _chk(cancel_event)
    _st("Invited me 클릭 중...")
    _click(driver, wait,
        xpath=f"//*[contains({_ci('text()')}, 'invited me')]",
        label="Invited me",
    )
    time.sleep(1.5)

    # ── Step 5: Confirm to follow the order 클릭 ─────────────────
    _chk(cancel_event)
    _st("Confirm to follow the order 클릭 중...")
    try:
        _click(driver, wait,
            xpath=f"//*[contains({_ci('text()')}, 'confirm to follow')]",
            label="Confirm to follow the order",
        )
        time.sleep(1.5)
    except RuntimeError:
        _st("⚠ Confirm to follow the order 버튼 미표시 — 다음 계정으로 건너뜀")
        return

    # ── Step 6: Done / OK 클릭 ───────────────────────────────────
    _chk(cancel_event)
    _st("Done/OK 클릭 중...")
    try:
        _click(driver, wait,
            xpath=(
                f"//*["
                f"  contains({_ci('text()')}, 'done')"
                f"  or contains({_ci('text()')}, 'ok')"
                f"]"
            ),
            label="Done/OK 버튼",
        )
        time.sleep(0.5)
    except RuntimeError:
        _st("✗ Done/OK 버튼 미표시 — 실패")
        raise RuntimeError("Done/OK 버튼이 나타나지 않았습니다.")

    # ── Step 7: "Already followed the order" 팝업 확인 ──────────
    _chk(cancel_event)
    _st("완료 팝업 대기 중...")
    try:
        wait.until(EC.presence_of_element_located((
            By.XPATH,
            f"//*[contains({_ci('text()')}, 'already followed')]",
        )))
        _st("✓ Already followed the order — 완료!")
    except TimeoutException:
        raise RuntimeError("완료 팝업(Already followed the order)이 나타나지 않았습니다.")


def click_no_more(
    port: int = 9222,           # 하위 호환용, 현재 미사용
    login_url=LOGIN_URL,        # str 또는 list[str]
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
    proxy: str = "",
) -> None:
    """
    No more → Done/OK 흐름 실행.
    login_url이 리스트인 경우 실패 시 다음 URL로 순서대로 시도.
    LoginFailed 발생 시 다음 사이트 시도 없이 즉시 예외 전파.
    """
    _chk(cancel_event)

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
        _chk(cancel_event)
        if len(urls) > 1:
            _st(f"[{idx+1}/{len(urls)}] {url}")
        driver = _open_driver(status_cb, proxy=proxy)
        try:
            _do_no_more(driver, url, email, password, _st, cancel_event)
            _st("No more 완료!")
            return
        except AutoCancelled:
            raise
        except LoginFailed:
            raise
        except InvalidParameter:
            raise
        except Exception as e:
            last_error = e
            _st(f"✗ 사이트 {idx+1} 실패: [{type(e).__name__}] {e}")
        finally:
            try:
                driver.quit()
                logger.info("Chrome 종료")
            except Exception:
                pass
        if idx < len(urls) - 1:
            _st("다음 사이트로 재시도...")

    raise RuntimeError(f"모든 사이트({len(urls)}개) 실패: {last_error}")
