"""
카카오 메시지 모니터 — tkinter GUI 앱

실행: python app.py
설정: config.json (자동 저장/복원)
"""
import json
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

# exe(frozen) 실행 시 sys.executable 기준, 스크립트 실행 시 __file__ 기준
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

from src.logger_config import setup_logger
from src.message_monitor import run_monitor
from src.message_parser import ChatMessage

try:
    from src.browser_controller import AutoCancelled, submit_order_code
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_CONFIG = {
    "room_name": "",
    "poll_interval": 3,
    "watch_sender": "",
    "auto_input": False,
    "chrome_port": 9222,
    "site_urls": ["https://dsj44.com/h5/#/login", "", "", "", ""],
}

# 영문+숫자 9자리 정확히 일치
CODE_PATTERN = re.compile(r'^[A-Za-z0-9]{9}$')

logger = setup_logger("app")


# ---------------------------------------------------------------------------
# 설정 로드 / 저장
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"설정 저장 실패: {e}")


# ---------------------------------------------------------------------------
# GUI 앱
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("카카오 메시지 모니터")
        self.resizable(True, True)
        self.minsize(540, 640)

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._auto_cancel_event: threading.Event = threading.Event()
        self._msg_queue: queue.Queue = queue.Queue()
        self._caught_history: list = []
        self._processed_codes: set = set()  # 중복 실행 방지

        cfg = load_config()
        self._build_ui(cfg)
        self._poll_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self, cfg: dict) -> None:
        # ── 카카오 모니터링 설정 ──────────────────────────────────────
        setting_frame = ttk.LabelFrame(self, text="모니터링 설정", padding=8)
        setting_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        setting_frame.columnconfigure(1, weight=1)

        ttk.Label(setting_frame, text="채팅방 이름:").grid(
            row=0, column=0, sticky=tk.W, pady=2)
        self._room_var = tk.StringVar(value=cfg["room_name"])
        ttk.Entry(setting_frame, textvariable=self._room_var).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, padx=(6, 0), pady=2)

        ttk.Label(setting_frame, text="폴링 간격:").grid(
            row=1, column=0, sticky=tk.W, pady=2)
        interval_row = ttk.Frame(setting_frame)
        interval_row.grid(row=1, column=1, sticky=tk.W, padx=(6, 0), pady=2)
        self._interval_var = tk.StringVar(value=str(cfg["poll_interval"]))
        ttk.Entry(interval_row, textvariable=self._interval_var, width=6).pack(side=tk.LEFT)
        ttk.Label(interval_row, text="초").pack(side=tk.LEFT, padx=4)

        ttk.Label(setting_frame, text="발신자 필터:").grid(
            row=2, column=0, sticky=tk.W, pady=2)
        self._sender_var = tk.StringVar(value=cfg["watch_sender"])
        ttk.Entry(setting_frame, textvariable=self._sender_var).grid(
            row=2, column=1, sticky=tk.EW, padx=(6, 0), pady=2)
        ttk.Label(setting_frame, text="(비워두면 전체)", foreground="gray").grid(
            row=2, column=2, sticky=tk.W, padx=4)

        self._topmost_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            setting_frame, text="항상 위",
            variable=self._topmost_var, command=self._toggle_topmost,
        ).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        # ── 자동 입력 설정 ────────────────────────────────────────────
        auto_frame = ttk.LabelFrame(self, text="자동 입력 설정 (Chrome 원격 디버깅)", padding=8)
        auto_frame.pack(fill=tk.X, padx=10, pady=4)
        auto_frame.columnconfigure(1, weight=1)

        self._auto_var = tk.BooleanVar(value=cfg.get("auto_input", False))
        auto_check = ttk.Checkbutton(
            auto_frame,
            text="코드 캐치 시 자동으로 사이트에 입력",
            variable=self._auto_var,
        )
        auto_check.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))

        if not SELENIUM_OK:
            ttk.Label(auto_frame, text="⚠ selenium 미설치 — 자동 입력 불가",
                      foreground="#f44747").grid(
                row=1, column=0, columnspan=3, sticky=tk.W)
            self._auto_var.set(False)
            auto_check.config(state=tk.DISABLED)

        # 사이트 주소 5개 (실패 시 순서대로 시도)
        saved_urls = cfg.get("site_urls", DEFAULT_CONFIG["site_urls"])
        # 구버전 config 호환 (site_url 단일 문자열)
        if isinstance(saved_urls, str):
            saved_urls = [saved_urls, "", "", "", ""]
        while len(saved_urls) < 5:
            saved_urls.append("")

        self._site_url_vars = []
        for i in range(5):
            ttk.Label(auto_frame, text=f"사이트 {i+1}:").grid(
                row=2 + i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=saved_urls[i])
            self._site_url_vars.append(var)
            ttk.Entry(auto_frame, textvariable=var).grid(
                row=2 + i, column=1, columnspan=2, sticky=tk.EW, padx=(6, 0), pady=2)

        ttk.Label(auto_frame, text="Chrome 포트:").grid(
            row=7, column=0, sticky=tk.W, pady=2)
        port_row = ttk.Frame(auto_frame)
        port_row.grid(row=7, column=1, sticky=tk.W, padx=(6, 0), pady=2)
        self._port_var = tk.StringVar(value=str(cfg.get("chrome_port", 9222)))
        ttk.Entry(port_row, textvariable=self._port_var, width=7).pack(side=tk.LEFT)
        ttk.Label(port_row, text="(기본 9222)", foreground="gray").pack(
            side=tk.LEFT, padx=6)

        # ── 제어 버튼 ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=4)

        self._start_btn = ttk.Button(
            btn_frame, text="▶ 모니터링 시작", command=self._start_monitor)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 4))

        self._stop_btn = ttk.Button(
            btn_frame, text="■ 중지", command=self._stop_monitor, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_frame, text="로그 지우기", command=self._clear_log).pack(
            side=tk.LEFT, padx=4)

        # ── 캐치 패널 ─────────────────────────────────────────────────
        catch_frame = ttk.LabelFrame(self, text="캐치된 코드  (영숫자 9자리)", padding=8)
        catch_frame.pack(fill=tk.X, padx=10, pady=4)

        code_box = tk.Frame(catch_frame, bg="#0d1117", relief=tk.FLAT, bd=1)
        code_box.pack(fill=tk.X, pady=(0, 6))

        self._latest_code_var = tk.StringVar(value="—")
        tk.Label(code_box, textvariable=self._latest_code_var,
                 font=("Consolas", 36, "bold"), fg="#f0c040", bg="#0d1117",
                 pady=12).pack()

        self._latest_meta_var = tk.StringVar(value="대기 중...")
        tk.Label(code_box, textvariable=self._latest_meta_var,
                 font=("Consolas", 9), fg="#8b949e", bg="#0d1117",
                 pady=2).pack()

        hist_frame = tk.Frame(catch_frame, bg=self.cget("bg"))
        hist_frame.pack(fill=tk.X)
        tk.Label(hist_frame, text="이전:", font=("Consolas", 9), fg="gray").pack(side=tk.LEFT)
        self._history_var = tk.StringVar(value="없음")
        tk.Label(hist_frame, textvariable=self._history_var,
                 font=("Consolas", 9), fg="#4ec9b0").pack(side=tk.LEFT, padx=4)

        # ── 전체 메시지 로그 ──────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="전체 메시지 로그", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._log = tk.Text(
            log_frame, state=tk.DISABLED,
            background="#1e1e1e", foreground="#d4d4d4",
            insertbackground="#d4d4d4", relief=tk.FLAT,
            wrap=tk.WORD, font=("Consolas", 10),
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.pack(fill=tk.BOTH, expand=True)

        self._log.tag_configure("timestamp", foreground="#569cd6")
        self._log.tag_configure("sender", foreground="#4ec9b0",
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("system", foreground="#6a9955",
                                font=("Consolas", 10, "italic"))
        self._log.tag_configure("error", foreground="#f44747")
        self._log.tag_configure("caught_code", foreground="#f0c040",
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("auto_ok", foreground="#4ec9b0",
                                font=("Consolas", 10, "italic"))

        # ── 상태바 ────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="대기 중")
        ttk.Label(self, textvariable=self._status_var,
                  relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # 제어
    # ------------------------------------------------------------------

    def _start_monitor(self) -> None:
        room_name = self._room_var.get().strip()
        if not room_name:
            self._append_log("채팅방 이름을 입력하세요.", tag="error")
            return

        try:
            poll_interval = float(self._interval_var.get())
        except ValueError:
            self._append_log("폴링 간격은 숫자로 입력하세요.", tag="error")
            return

        watch_sender = self._sender_var.get().strip()

        try:
            chrome_port = int(self._port_var.get())
        except ValueError:
            chrome_port = 9222

        save_config({
            "room_name": room_name,
            "poll_interval": poll_interval,
            "watch_sender": watch_sender,
            "auto_input": self._auto_var.get(),
            "chrome_port": chrome_port,
            "site_urls": [v.get().strip() for v in self._site_url_vars],
        })

        self._stop_event = threading.Event()
        self._auto_cancel_event.clear()  # 이전 취소 상태 초기화
        self._monitor_thread = threading.Thread(
            target=run_monitor,
            kwargs={
                "room_name": room_name,
                "poll_interval": poll_interval,
                "watch_sender": watch_sender,
                "on_new_message": self._on_new_message,
                "stop_event": self._stop_event,
            },
            daemon=True,
        )
        self._monitor_thread.start()

        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._status_var.set(f"모니터링 중 | 채팅방: {room_name}")
        self._append_log(f"── 모니터링 시작: '{room_name}' ──", tag="system")

    def _stop_monitor(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        self._auto_cancel_event.set()  # 진행 중인 자동 입력도 취소
        self._processed_codes.clear()
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._status_var.set("중지됨")
        self._append_log("── 모니터링 중지 ──", tag="system")

    def _clear_log(self) -> None:
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.config(state=tk.DISABLED)

    def _toggle_topmost(self) -> None:
        self.attributes("-topmost", self._topmost_var.get())

    def _on_close(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        self.destroy()

    # ------------------------------------------------------------------
    # 스레드 → GUI
    # ------------------------------------------------------------------

    def _on_new_message(self, msg: ChatMessage) -> None:
        self._msg_queue.put(msg)

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._msg_queue.get_nowait()
                if isinstance(item, ChatMessage):
                    self._handle_message(item)
                elif isinstance(item, tuple):
                    # (tag, text) 형식
                    tag, text = item
                    self._append_log(text, tag=tag)
                elif isinstance(item, str):
                    self._append_log(item, tag="system")
        except queue.Empty:
            pass

        if (
            self._monitor_thread is not None
            and not self._monitor_thread.is_alive()
            and self._stop_btn["state"] == tk.NORMAL
        ):
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_var.set("모니터링 종료 (오류 또는 정상 종료)")
            self._monitor_thread = None

        self.after(200, self._poll_queue)

    # ------------------------------------------------------------------
    # 메시지 처리
    # ------------------------------------------------------------------

    def _handle_message(self, msg: ChatMessage) -> None:
        code = msg.content.strip()
        is_code = bool(CODE_PATTERN.match(code))

        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, f"[{msg.timestamp_str}] ", "timestamp")
        self._log.insert(tk.END, f"{msg.sender}", "sender")
        self._log.insert(tk.END, ": ")
        if is_code:
            self._log.insert(tk.END, f"{code}  ★\n", "caught_code")
        else:
            self._log.insert(tk.END, f"{msg.content}\n")
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

        if is_code:
            self._update_catch_panel(code, msg.timestamp_str, msg.sender)

    def _update_catch_panel(self, code: str, ts: str, sender: str) -> None:
        current = self._latest_code_var.get()
        if current != "—":
            self._caught_history.insert(0, current)
            self._caught_history = self._caught_history[:8]

        self._latest_code_var.set(code)
        self._latest_meta_var.set(f"{ts}  |  {sender}")

        if self._caught_history:
            self._history_var.set("  ".join(self._caught_history))
        else:
            self._history_var.set("없음")

        self._status_var.set(f"코드 캐치: {code}  ({ts} / {sender})")

        # 자동 입력 트리거 (중복 코드 무시)
        if not SELENIUM_OK:
            self._append_log("⚠ selenium 미설치 — 자동 입력 불가", tag="error")
            return
        if not self._auto_var.get():
            self._append_log("ℹ 자동 입력 비활성 (체크박스 확인)", tag="system")
            return
        if SELENIUM_OK and self._auto_var.get():
            if code in self._processed_codes:
                self._append_log(f"중복 코드 무시: {code}", tag="system")
                return
            self._processed_codes.add(code)
            try:
                port = int(self._port_var.get())
            except ValueError:
                port = 9222
            site_urls = [v.get().strip() for v in self._site_url_vars if v.get().strip()]
            if not site_urls:
                self._append_log("⚠ 사이트 주소를 입력하세요.", tag="error")
                return
            threading.Thread(
                target=self._run_auto_input,
                args=(code, port, site_urls),
                daemon=True,
            ).start()

    def _run_auto_input(self, code: str, port: int, site_url: str) -> None:
        """백그라운드 스레드에서 브라우저 자동 입력 실행."""
        if self._auto_cancel_event.is_set():
            return  # 시작 전 이미 취소됨

        self._msg_queue.put(("system", f"→ 자동 입력 시도: {code}"))

        def _status(msg: str) -> None:
            self._msg_queue.put(("system", f"  · {msg}"))

        try:
            submit_order_code(
                code, port, site_url,
                status_cb=_status,
                cancel_event=self._auto_cancel_event,
            )
            self._msg_queue.put(("auto_ok", f"✓ 자동 입력 완료: {code}"))
        except AutoCancelled:
            self._msg_queue.put(("system", "── 자동 입력 취소됨 ──"))
        except Exception as e:
            self._msg_queue.put(("error", f"✗ 자동 입력 실패: {e}"))

    # ------------------------------------------------------------------
    # 로그 출력
    # ------------------------------------------------------------------

    def _append_log(self, text: str, tag: str = "") -> None:
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, text + "\n", tag if tag else ())
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
