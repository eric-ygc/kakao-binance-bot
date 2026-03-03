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
from tkinter import messagebox, ttk
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
    "accounts": [],
    "account_index": 0,
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

        # 계정 상태 (_build_ui 전 초기화)
        self._accounts: list = list(cfg.get("accounts", []))
        self._account_idx: int = int(cfg.get("account_index", 0))
        if self._account_idx >= len(self._accounts):
            self._account_idx = 0

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
        auto_frame = ttk.LabelFrame(self, text="자동 입력 설정", padding=8)
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

        # ── 현재 계정 표시 + 계정 관리 버튼 ─────────────────────────
        ttk.Label(auto_frame, text="현재 계정:").grid(
            row=8, column=0, sticky=tk.W, pady=(6, 2))
        self._current_acct_var = tk.StringVar()
        ttk.Label(auto_frame, textvariable=self._current_acct_var,
                  foreground="#4ec9b0").grid(
            row=8, column=1, sticky=tk.W, padx=(6, 0), pady=(6, 2))
        ttk.Button(auto_frame, text="계정 관리",
                   command=self._open_account_manager).grid(
            row=8, column=2, sticky=tk.E, padx=(4, 0), pady=(6, 2))

        self._update_current_acct_label()

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
    # 설정 헬퍼
    # ------------------------------------------------------------------

    def _get_current_config(self) -> dict:
        try:
            poll_interval = float(self._interval_var.get())
        except ValueError:
            poll_interval = DEFAULT_CONFIG["poll_interval"]
        try:
            chrome_port = int(self._port_var.get())
        except ValueError:
            chrome_port = 9222
        return {
            "room_name": self._room_var.get().strip(),
            "poll_interval": poll_interval,
            "watch_sender": self._sender_var.get().strip(),
            "auto_input": self._auto_var.get(),
            "chrome_port": chrome_port,
            "site_urls": [v.get().strip() for v in self._site_url_vars],
            "accounts": self._accounts,
            "account_index": self._account_idx,
        }

    # ------------------------------------------------------------------
    # 계정 관리
    # ------------------------------------------------------------------

    def _update_current_acct_label(self) -> None:
        if not self._accounts:
            self._current_acct_var.set("(등록된 계정 없음 — 계정 관리에서 추가)")
        else:
            idx = self._account_idx % len(self._accounts)
            acct = self._accounts[idx]
            self._current_acct_var.set(
                f"▶  [{idx + 1}/{len(self._accounts)}]  {acct['email']}")

    def _open_account_manager(self) -> None:
        def on_save(accounts, current_idx):
            self._accounts = accounts
            self._account_idx = current_idx
            self._update_current_acct_label()
            save_config(self._get_current_config())

        AccountManagerDialog(self, self._accounts, self._account_idx, on_save)

    def _advance_account(self) -> None:
        """성공 후 다음 계정으로 전환."""
        if self._accounts:
            self._account_idx = (self._account_idx + 1) % len(self._accounts)
            self.after(0, self._update_current_acct_label)
            save_config(self._get_current_config())

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

        save_config(self._get_current_config())

        self._stop_event = threading.Event()
        self._auto_cancel_event.clear()
        self._monitor_thread = threading.Thread(
            target=run_monitor,
            kwargs={
                "room_name": room_name,
                "poll_interval": poll_interval,
                "watch_sender": self._sender_var.get().strip(),
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
        self._auto_cancel_event.set()
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
        save_config(self._get_current_config())
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

        if not SELENIUM_OK:
            self._append_log("⚠ selenium 미설치 — 자동 입력 불가", tag="error")
            return
        if not self._auto_var.get():
            self._append_log("ℹ 자동 입력 비활성 (체크박스 확인)", tag="system")
            return
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

    def _run_auto_input(self, code: str, port: int, site_urls: list) -> None:
        """백그라운드 스레드에서 브라우저 자동 입력 실행 — 등록된 계정 전부 순차 처리."""
        if self._auto_cancel_event.is_set():
            return

        if not self._accounts:
            self._msg_queue.put(("error", "⚠ 등록된 계정이 없습니다. [계정 관리]에서 추가하세요."))
            return

        accounts = list(self._accounts)  # 스레드 시작 시점 스냅샷
        total = len(accounts)
        self._msg_queue.put(("system", f"━━ 자동 입력 시작: {code} | 총 {total}개 계정 순차 처리 ━━"))

        success_count = 0
        fail_count = 0

        for i, acct in enumerate(accounts):
            if self._auto_cancel_event.is_set():
                self._msg_queue.put(("system", "── 자동 입력 취소됨 ──"))
                return

            acct_label = f"[{i + 1}/{total}] {acct['email']}"
            self._msg_queue.put(("system", f"→ {acct_label} 처리 중..."))

            def _status(msg: str) -> None:
                self._msg_queue.put(("system", f"  · {msg}"))

            try:
                submit_order_code(
                    code, port, site_urls,
                    email=acct["email"],
                    password=acct["password"],
                    status_cb=_status,
                    cancel_event=self._auto_cancel_event,
                )
                self._msg_queue.put(("auto_ok", f"✓ 완료: {acct_label}"))
                success_count += 1
            except AutoCancelled:
                self._msg_queue.put(("system", "── 자동 입력 취소됨 ──"))
                return
            except Exception as e:
                self._msg_queue.put(("error", f"✗ 실패: {acct_label} — {e}"))
                fail_count += 1

        self._msg_queue.put((
            "auto_ok" if fail_count == 0 else "system",
            f"━━ 전체 완료: {code} | 성공 {success_count} / 실패 {fail_count} / 총 {total} ━━",
        ))

    # ------------------------------------------------------------------
    # 로그 출력
    # ------------------------------------------------------------------

    def _append_log(self, text: str, tag: str = "") -> None:
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, text + "\n", tag if tag else ())
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# 계정 관리 다이얼로그
# ---------------------------------------------------------------------------

class _AccountEditDialog(tk.Toplevel):
    """계정 추가/수정 단순 다이얼로그."""

    def __init__(self, parent, account: dict = None) -> None:
        super().__init__(parent)
        self.title("계정 추가" if account is None else "계정 수정")
        self.resizable(False, False)
        self.grab_set()
        self.result: Optional[dict] = None

        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="이메일:").grid(
            row=0, column=0, padx=12, pady=8, sticky=tk.W)
        self._email_var = tk.StringVar(value=account["email"] if account else "")
        ttk.Entry(self, textvariable=self._email_var, width=32).grid(
            row=0, column=1, padx=(0, 12), pady=8, sticky=tk.EW)

        ttk.Label(self, text="비밀번호:").grid(
            row=1, column=0, padx=12, pady=4, sticky=tk.W)
        self._pw_var = tk.StringVar(value=account["password"] if account else "")
        self._pw_entry = ttk.Entry(self, textvariable=self._pw_var, width=32, show="*")
        self._pw_entry.grid(row=1, column=1, padx=(0, 12), pady=4, sticky=tk.EW)

        self._show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self, text="비밀번호 표시", variable=self._show_pw,
            command=lambda: self._pw_entry.config(
                show="" if self._show_pw.get() else "*")
        ).grid(row=2, column=1, sticky=tk.W, padx=(0, 12), pady=(0, 4))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="확인", command=self._ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side=tk.LEFT, padx=6)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

        # 이메일 필드에 포커스
        self.after(50, lambda: self._email_var and None)

    def _ok(self) -> None:
        email = self._email_var.get().strip()
        if not email:
            messagebox.showwarning("입력 오류", "이메일을 입력하세요.", parent=self)
            return
        self.result = {"email": email, "password": self._pw_var.get()}
        self.destroy()


class AccountManagerDialog(tk.Toplevel):
    """최대 50개 계정 목록 관리 다이얼로그."""

    def __init__(self, parent, accounts: list, current_idx: int,
                 on_save) -> None:
        super().__init__(parent)
        self.title("계정 목록 관리")
        self.resizable(True, True)
        self.minsize(460, 420)
        self.grab_set()

        self._accounts: list = list(accounts)   # 작업 복사본
        self._current_idx: int = current_idx
        self._on_save = on_save

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text="최대 50개 등록 가능. 코드 수신 시 현재(▶) 계정부터 순차 사용.",
            foreground="gray",
        ).pack(padx=10, pady=(8, 2), anchor=tk.W)

        # Treeview
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        cols = ("no", "email", "password")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=16)
        self._tree.heading("no", text="No.")
        self._tree.heading("email", text="이메일")
        self._tree.heading("password", text="비밀번호")
        self._tree.column("no", width=55, anchor="center", stretch=False)
        self._tree.column("email", width=230)
        self._tree.column("password", width=100, stretch=False)

        sb = ttk.Scrollbar(tree_frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.tag_configure("current", foreground="#4ec9b0")

        # 버튼
        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=10, pady=(4, 10))

        ttk.Button(btn_frame, text="추가", command=self._add).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="수정", command=self._edit).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="삭제", command=self._delete).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="현재로 설정",
                   command=self._set_current).pack(side=tk.LEFT, padx=3)
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(btn_frame, text="저장 후 닫기",
                   command=self._save_close).pack(side=tk.LEFT, padx=3)

    def _refresh_list(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, acct in enumerate(self._accounts):
            marker = "▶" if i == self._current_idx else f"{i + 1}"
            masked = "•" * min(len(acct.get("password", "")), 8) or "(없음)"
            tags = ("current",) if i == self._current_idx else ()
            self._tree.insert(
                "", tk.END, iid=str(i),
                values=(marker, acct.get("email", ""), masked),
                tags=tags,
            )

        # 현재 계정으로 스크롤
        if self._accounts and 0 <= self._current_idx < len(self._accounts):
            self._tree.selection_set(str(self._current_idx))
            self._tree.see(str(self._current_idx))

    def _selected_idx(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self) -> None:
        if len(self._accounts) >= 50:
            messagebox.showwarning(
                "최대 50개", "계정은 최대 50개까지 등록 가능합니다.", parent=self)
            return
        dlg = _AccountEditDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self._accounts.append(dlg.result)
            self._refresh_list()

    def _edit(self) -> None:
        idx = self._selected_idx()
        if idx is None:
            return
        dlg = _AccountEditDialog(self, self._accounts[idx])
        self.wait_window(dlg)
        if dlg.result:
            self._accounts[idx] = dlg.result
            self._refresh_list()

    def _delete(self) -> None:
        idx = self._selected_idx()
        if idx is None:
            return
        if not messagebox.askyesno(
                "삭제 확인",
                f"계정 {idx + 1} ({self._accounts[idx]['email']})을 삭제하시겠습니까?",
                parent=self):
            return
        self._accounts.pop(idx)
        if self._current_idx >= len(self._accounts):
            self._current_idx = max(0, len(self._accounts) - 1)
        self._refresh_list()

    def _set_current(self) -> None:
        idx = self._selected_idx()
        if idx is None:
            return
        self._current_idx = idx
        self._refresh_list()

    def _save_close(self) -> None:
        self._on_save(self._accounts, self._current_idx)
        self.destroy()


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
