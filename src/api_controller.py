"""
dsj44.com API 자동화 모듈 (curl_cffi 기반, Selenium 없이 동작).

흐름 A -- 코드 입력 (submit_order_code):
  1. POST /api/app/user/login  -> 토큰 획득
  2. POST /api/app/second/share/user/follow/code  -> 코드 제출

흐름 B -- 보너스픽 (click_no_more):
  (API 엔드포인트 확인 필요 -- 현재 미구현, Selenium 폴백 사용)
"""

import logging
import time
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests

from src.exceptions import AutoCancelled, InvalidParameter, LoginFailed

logger = logging.getLogger("api_controller")

# ── 상수 ──────────────────────────────────────────────
API_HOST = "https://api.ddjea.com"
LOGIN_ENDPOINT = f"{API_HOST}/api/app/user/login"
CODE_ENDPOINT = f"{API_HOST}/api/app/second/share/user/follow/code"
LOGIN_URL = "https://dsj44.com/h5/#/login"

RETRY_COUNT = 3
RETRY_WAIT = 5
CODE_RETRY_COUNT = 6   # 코드 제출 "Frequent requests" 재시도 횟수
CODE_RETRY_WAIT = 3    # 코드 제출 재시도 대기 (초)


# ── 내부 헬퍼 ─────────────────────────────────────────

def _chk(cancel_event):
    """취소 이벤트 확인."""
    if cancel_event and cancel_event.is_set():
        raise AutoCancelled()


def _build_headers(site_url: str, token: str = "") -> dict:
    """브라우저에서 캡처한 정확한 헤더 생성."""
    parsed = urlparse(site_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "APP-ANALOG": "false",
        "APP-CLIENT-TIMEZONE": "+8",
        "APP-LOGIN-TOKEN": token,
        "APP-VERSION": "P2.9.3",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "REQUEST-DOMAIN": site_url,
        "Referer": f"{origin}/",
        "SET-LANGUAGE": "ENGLISH",
        "X-Requested-With": "XMLHttpRequest",
        "aws-check": "true",
        "set-aws": "true",
        "Origin": origin,
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def _normalize_proxy(proxy: str) -> str:
    """다양한 프록시 형식 -> http://user:pass@host:port"""
    if not proxy or not proxy.strip():
        return ""
    proxy = proxy.strip()
    if proxy.startswith("http://") or proxy.startswith("https://"):
        return proxy
    parts = proxy.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{proxy}"
    return proxy


def _make_proxies(proxy: str) -> dict:
    """curl_cffi용 proxies 딕셔너리 생성."""
    url = _normalize_proxy(proxy)
    if not url:
        return {}
    return {"http": url, "https": url}


def _api_login(
    email: str,
    password: str,
    site_url: str,
    proxy: str,
    _st,
    cancel_event,
) -> str:
    """로그인 후 토큰 반환. 실패 시 예외."""
    proxies = _make_proxies(proxy)

    for attempt in range(RETRY_COUNT):
        _chk(cancel_event)
        try:
            resp = cffi_requests.post(
                LOGIN_ENDPOINT,
                json={"password": password, "isValidator": True, "email": email},
                headers=_build_headers(site_url),
                proxies=proxies or None,
                impersonate="chrome131",
                timeout=20,
            )
        except Exception as e:
            if attempt < RETRY_COUNT - 1:
                _st(f"연결 오류 — {RETRY_WAIT}초 후 재시도 ({attempt + 1}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
                continue
            raise RuntimeError(f"API 연결 실패: {e}")

        if resp.status_code == 429:
            _st(f"429 Too Many Requests — {RETRY_WAIT}초 대기 ({attempt + 1}/{RETRY_COUNT})")
            time.sleep(RETRY_WAIT)
            continue

        data = resp.json()
        if data.get("resultCode"):
            return data["data"]  # 토큰

        err_msg = data.get("errCodeDes", str(data))
        if "not exist" in err_msg.lower() or "password" in err_msg.lower():
            raise LoginFailed(f"{err_msg} ({email})")
        if attempt < RETRY_COUNT - 1:
            _st(f"로그인 실패: {err_msg} — 재시도 ({attempt + 1}/{RETRY_COUNT})")
            time.sleep(RETRY_WAIT)
            continue
        raise LoginFailed(f"{err_msg} ({email})")

    raise LoginFailed(f"로그인 재시도 초과 ({email})")


def _api_submit_code(
    token: str,
    code: str,
    site_url: str,
    proxy: str,
    _st,
    cancel_event,
) -> None:
    """코드 제출. Frequent requests 시 같은 토큰으로 재시도."""
    proxies = _make_proxies(proxy)

    for attempt in range(CODE_RETRY_COUNT):
        _chk(cancel_event)

        try:
            resp = cffi_requests.post(
                CODE_ENDPOINT,
                json={"code": code},
                headers=_build_headers(site_url, token),
                proxies=proxies or None,
                impersonate="chrome131",
                timeout=20,
            )
        except Exception as e:
            raise RuntimeError(f"코드 제출 연결 실패: {e}")

        data = resp.json()
        if data.get("resultCode"):
            return  # 성공

        err = data.get("errCodeDes", "")
        if "invalid" in err.lower():
            raise InvalidParameter(f"Invalid parameter — {err}")

        # "Frequent requests" → 같은 토큰으로 대기 후 재시도
        if "frequent" in err.lower() or resp.status_code == 429:
            if attempt < CODE_RETRY_COUNT - 1:
                wait = CODE_RETRY_WAIT * (attempt + 1)  # 점진적 대기: 3, 6, 9, 12, 15초
                _st(f"Frequent requests — {wait}초 대기 후 재시도 ({attempt + 1}/{CODE_RETRY_COUNT})")
                time.sleep(wait)
                continue
            raise RuntimeError(f"코드 제출 실패 (재시도 초과): {err}")

        raise RuntimeError(f"코드 제출 실패: {err}")


# ── 공개 API (browser_controller.py와 동일한 시그니처) ──

def submit_order_code(
    code: str,
    port: int = 9222,
    login_url=LOGIN_URL,
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
    proxy: str = "",
) -> None:
    """코드 자동 입력 (API 방식).

    browser_controller.submit_order_code와 동일한 시그니처.
    """
    _chk(cancel_event)

    def _st(msg: str) -> None:
        logger.info(msg)
        if status_cb:
            status_cb(msg)

    # URL 목록 정리
    if isinstance(login_url, str):
        urls = [login_url] if login_url.strip() else []
    else:
        urls = [u.strip() for u in login_url if u.strip()]
    if not urls:
        urls = [LOGIN_URL]

    _st(f"API 자동 입력 | code={code} | 계정={email}")

    last_error = None
    for idx, url in enumerate(urls):
        _chk(cancel_event)
        if len(urls) > 1:
            _st(f"[{idx + 1}/{len(urls)}] {url}")

        try:
            # Step 1: 로그인
            _st(f"로그인 중: {email}")
            token = _api_login(email, password, url, proxy, _st, cancel_event)
            _st("로그인 성공")

            # Step 2: 코드 제출
            _chk(cancel_event)
            _st(f"코드 제출 중: {code}")
            _api_submit_code(token, code, url, proxy, _st, cancel_event)
            _st("자동 입력 완료!")
            return

        except AutoCancelled:
            raise  # 취소는 즉시 전파

        except (LoginFailed, InvalidParameter) as e:
            last_error = e
            _st(f"사이트 {idx + 1} 로그인 실패: {e}")

        except Exception as e:
            last_error = e
            _st(f"사이트 {idx + 1} 실패: [{type(e).__name__}] {e}")

        if idx < len(urls) - 1:
            _st("다음 사이트로 재시도...")

    raise RuntimeError(f"모든 사이트({len(urls)}개) 실패: {last_error}")


def click_no_more(
    port: int = 9222,
    login_url=LOGIN_URL,
    email: str = "",
    password: str = "",
    status_cb=None,
    cancel_event=None,
    proxy: str = "",
) -> None:
    """보너스픽 (API) — 엔드포인트 확인 후 구현 예정."""
    raise NotImplementedError("보너스픽 API 미구현 — Selenium 폴백 사용")
