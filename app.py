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

CODE_PATTERN = re.compile(r'^[A-Za-z0-9]{9}$')
logger = setup_logger("app")

# ---------------------------------------------------------------------------
# 다크 테마 색상 팔레트
# ---------------------------------------------------------------------------
C = {
    "bg":          "#1e1e1e",   # 메인 배경
    "panel":       "#252526",   # LabelFrame 내부
    "panel2":      "#2d2d30",   # 버튼·입력 배경
    "input":       "#3c3c3c",   # Entry 배경
    "border":      "#454545",   # 테두리
    "fg":          "#cccccc",   # 일반 텍스트
    "fg_dim":      "#888888",   # 보조 텍스트
    "fg_bright":   "#e8e8e8",   # 강조 텍스트
    "accent":      "#4ec9b0",   # 청록 강조
    "yellow":      "#f0c040",   # 코드 색상
    "code_bg":     "#0d1117",   # 코드 패널 배경
    "log_bg":      "#1a1a1a",   # 로그 배경
    "start":       "#2d6a2d",   # 시작 버튼
    "start_hl":    "#3d8a3d",
    "stop":        "#7a1f1f",   # 중지 버튼
    "stop_hl":     "#9a2f2f",
    "sel":         "#094771",   # 선택 색상
    "error":       "#f44747",
    "ok":          "#4ec9b0",
    "system":      "#6a9955",
}


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
        self.minsize(560, 680)
        self.configure(bg=C["bg"])

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._auto_cancel_event: threading.Event = threading.Event()
        self._msg_queue: queue.Queue = queue.Queue()
        self._caught_history: list = []
        self._processed_codes: set = set()

        cfg = load_config()
        self._accounts: list = list(cfg.get("accounts", []))
        self._account_idx: int = int(cfg.get("account_index", 0))
        if self._account_idx >= len(self._accounts):
            self._account_idx = 0

        self._apply_dark_theme()
        self._build_ui(cfg)
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # 다크 테마 적용
    # ------------------------------------------------------------------

    def _apply_dark_theme(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")

        # 전역 기본값
        s.configure(".",
            background=C["bg"],
            foreground=C["fg"],
            fieldbackground=C["input"],
            bordercolor=C["border"],
            darkcolor=C["panel"],
            lightcolor=C["panel"],
            troughcolor=C["panel"],
            selectbackground=C["sel"],
            selectforeground="#ffffff",
            insertcolor=C["fg"],
            relief="flat",
        )

        # Frame
        s.configure("TFrame", background=C["bg"])
        s.configure("Panel.TFrame", background=C["panel"])

        # Label
        s.configure("TLabel", background=C["bg"], foreground=C["fg"],
                    font=("Segoe UI", 9))
        s.configure("Panel.TLabel", background=C["panel"], foreground=C["fg"],
                    font=("Segoe UI", 9))
        s.configure("Dim.TLabel", background=C["panel"], foreground=C["fg_dim"],
                    font=("Segoe UI", 8))

        # LabelFrame
        s.configure("TLabelframe",
            background=C["panel"],
            bordercolor=C["border"],
            darkcolor=C["panel"],
            lightcolor=C["panel"],
            relief="groove",
        )
        s.configure("TLabelframe.Label",
            background=C["panel"],
            foreground=C["accent"],
            font=("Segoe UI", 9, "bold"),
        )

        # Entry
        s.configure("TEntry",
            fieldbackground=C["input"],
            foreground=C["fg_bright"],
            bordercolor=C["border"],
            insertcolor=C["fg"],
            padding=(4, 3),
        )
        s.map("TEntry",
            fieldbackground=[("readonly", C["panel"])],
            bordercolor=[("focus", C["accent"])],
        )

        # Checkbutton
        s.configure("TCheckbutton",
            background=C["panel"],
            foreground=C["fg"],
            focuscolor=C["panel"],
            font=("Segoe UI", 9),
        )
        s.map("TCheckbutton",
            background=[("active", C["panel"])],
            foreground=[("active", C["fg_bright"])],
        )

        # Button (기본)
        s.configure("TButton",
            background=C["panel2"],
            foreground=C["fg"],
            bordercolor=C["border"],
            darkcolor=C["panel2"],
            lightcolor=C["panel2"],
            padding=(10, 5),
            font=("Segoe UI", 9),
            relief="flat",
        )
        s.map("TButton",
            background=[("active", "#3f3f3f"), ("pressed", "#1a1a1a")],
            foreground=[("active", C["fg_bright"])],
            bordercolor=[("active", C["accent"])],
        )

        # 시작 버튼 (초록)
        s.configure("Start.TButton",
            background=C["start"],
            foreground="#ffffff",
            darkcolor=C["start"],
            lightcolor=C["start"],
            font=("Segoe UI", 9, "bold"),
        )
        s.map("Start.TButton",
            background=[("active", C["start_hl"]), ("pressed", "#1d4a1d")],
        )

        # 중지 버튼 (빨강)
        s.configure("Stop.TButton",
            background=C["stop"],
            foreground="#ffffff",
            darkcolor=C["stop"],
            lightcolor=C["stop"],
            font=("Segoe UI", 9, "bold"),
        )
        s.map("Stop.TButton",
            background=[("active", C["stop_hl"]), ("pressed", "#4b1010")],
        )

        # Scrollbar
        s.configure("TScrollbar",
            background=C["panel2"],
            troughcolor=C["panel"],
            bordercolor=C["border"],
            darkcolor=C["panel"],
            lightcolor=C["panel"],
            arrowcolor=C["fg_dim"],
            relief="flat",
        )
        s.map("TScrollbar",
            background=[("active", "#505050")],
        )

        # Separator
        s.configure("TSeparator", background=C["border"])

        # Treeview
        s.configure("Treeview",
            background="#2d2d2d",
            foreground=C["fg"],
            fieldbackground="#2d2d2d",
            bordercolor=C["border"],
            rowheight=26,
            font=("Segoe UI", 9),
        )
        s.configure("Treeview.Heading",
            background="#333333",
            foreground="#aaaaaa",
            bordercolor=C["border"],
            darkcolor="#333333",
            lightcolor="#333333",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        s.map("Treeview",
            background=[("selected", C["sel"])],
            foreground=[("selected", "#ffffff")],
        )
        s.map("Treeview.Heading",
            background=[("active", "#3d3d3d")],
        )

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self, cfg: dict) -> None:
        PAD = {"padx": 10, "pady": (6, 3)}

        # ── 모니터링 설정 ──────────────────────────────────────────
        sf = ttk.LabelFrame(self, text="  모니터링 설정", padding=(12, 8))
        sf.pack(fill=tk.X, **PAD)
        sf.columnconfigure(1, weight=1)

        ttk.Label(sf, text="채팅방 이름", style="Panel.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=3)
        self._room_var = tk.StringVar(value=cfg["room_name"])
        ttk.Entry(sf, textvariable=self._room_var).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=3)

        ttk.Label(sf, text="폴링 간격", style="Panel.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=3)
        ir = ttk.Frame(sf, style="Panel.TFrame")
        ir.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=3)
        self._interval_var = tk.StringVar(value=str(cfg["poll_interval"]))
        ttk.Entry(ir, textvariable=self._interval_var, width=6).pack(side=tk.LEFT)
        ttk.Label(ir, text=" 초", style="Panel.TLabel").pack(side=tk.LEFT)

        ttk.Label(sf, text="발신자 필터", style="Panel.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=3)
        self._sender_var = tk.StringVar(value=cfg["watch_sender"])
        ttk.Entry(sf, textvariable=self._sender_var).grid(
            row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=3)
        ttk.Label(sf, text="비워두면 전체", style="Dim.TLabel").grid(
            row=2, column=2, sticky=tk.W, padx=6)

        self._topmost_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="항상 위 표시",
                        variable=self._topmost_var,
                        command=self._toggle_topmost).grid(
            row=3, column=0, columnspan=3, sticky=tk.W, pady=(6, 2))

        # ── 자동 입력 설정 ─────────────────────────────────────────
        af = ttk.LabelFrame(self, text="  자동 입력 설정", padding=(12, 8))
        af.pack(fill=tk.X, **PAD)
        af.columnconfigure(1, weight=1)

        self._auto_var = tk.BooleanVar(value=cfg.get("auto_input", False))
        auto_chk = ttk.Checkbutton(af, text="코드 캐치 시 자동으로 사이트에 입력",
                                   variable=self._auto_var)
        auto_chk.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

        if not SELENIUM_OK:
            ttk.Label(af, text="⚠  selenium 미설치 — 자동 입력 불가",
                      style="Panel.TLabel",
                      foreground=C["error"]).grid(
                row=1, column=0, columnspan=3, sticky=tk.W)
            self._auto_var.set(False)
            auto_chk.config(state=tk.DISABLED)

        saved_urls = cfg.get("site_urls", DEFAULT_CONFIG["site_urls"])
        if isinstance(saved_urls, str):
            saved_urls = [saved_urls, "", "", "", ""]
        while len(saved_urls) < 5:
            saved_urls.append("")

        self._site_url_vars = []
        for i in range(5):
            ttk.Label(af, text=f"사이트 {i+1}", style="Panel.TLabel").grid(
                row=2+i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=saved_urls[i])
            self._site_url_vars.append(var)
            ttk.Entry(af, textvariable=var).grid(
                row=2+i, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=2)

        ttk.Label(af, text="Chrome 포트", style="Panel.TLabel").grid(
            row=7, column=0, sticky=tk.W, pady=(6, 2))
        pr = ttk.Frame(af, style="Panel.TFrame")
        pr.grid(row=7, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 2))
        self._port_var = tk.StringVar(value=str(cfg.get("chrome_port", 9222)))
        ttk.Entry(pr, textvariable=self._port_var, width=7).pack(side=tk.LEFT)
        ttk.Label(pr, text="  기본 9222", style="Dim.TLabel").pack(side=tk.LEFT)

        ttk.Label(af, text="현재 계정", style="Panel.TLabel").grid(
            row=8, column=0, sticky=tk.W, pady=(8, 2))
        self._current_acct_var = tk.StringVar()
        ttk.Label(af, textvariable=self._current_acct_var,
                  style="Panel.TLabel",
                  foreground=C["accent"]).grid(
            row=8, column=1, sticky=tk.W, padx=(8, 0), pady=(8, 2))
        ttk.Button(af, text="계정 관리",
                   command=self._open_account_manager).grid(
            row=8, column=2, sticky=tk.E, padx=(4, 0), pady=(8, 2))
        self._update_current_acct_label()

        # ── 제어 버튼 ──────────────────────────────────────────────
        bf = ttk.Frame(self)
        bf.pack(fill=tk.X, padx=10, pady=6)

        self._start_btn = ttk.Button(bf, text="▶  모니터링 시작",
                                     style="Start.TButton",
                                     command=self._start_monitor)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._stop_btn = ttk.Button(bf, text="■  중지",
                                    style="Stop.TButton",
                                    command=self._stop_monitor,
                                    state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=6)

        ttk.Button(bf, text="로그 지우기",
                   command=self._clear_log).pack(side=tk.LEFT, padx=6)

        # ── 캐치 코드 패널 ─────────────────────────────────────────
        cf = ttk.LabelFrame(self, text="  캐치된 코드  ( 영숫자 9자리 )", padding=(12, 8))
        cf.pack(fill=tk.X, padx=10, pady=(3, 3))

        code_box = tk.Frame(cf, bg=C["code_bg"], relief=tk.FLAT)
        code_box.pack(fill=tk.X, pady=(0, 6))

        self._latest_code_var = tk.StringVar(value="—")
        tk.Label(code_box, textvariable=self._latest_code_var,
                 font=("Consolas", 40, "bold"),
                 fg=C["yellow"], bg=C["code_bg"], pady=14).pack()

        self._latest_meta_var = tk.StringVar(value="대기 중...")
        tk.Label(code_box, textvariable=self._latest_meta_var,
                 font=("Segoe UI", 9), fg=C["fg_dim"], bg=C["code_bg"],
                 pady=4).pack()

        hist_row = tk.Frame(cf, bg=C["panel"])
        hist_row.pack(fill=tk.X, pady=(2, 0))
        tk.Label(hist_row, text="이전 코드:", font=("Segoe UI", 8),
                 fg=C["fg_dim"], bg=C["panel"]).pack(side=tk.LEFT)
        self._history_var = tk.StringVar(value="없음")
        tk.Label(hist_row, textvariable=self._history_var,
                 font=("Consolas", 9), fg=C["accent"], bg=C["panel"]).pack(
            side=tk.LEFT, padx=6)

        # ── 로그 ───────────────────────────────────────────────────
        lf = ttk.LabelFrame(self, text="  메시지 로그", padding=(4, 4))
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(3, 3))

        self._log = tk.Text(
            lf, state=tk.DISABLED,
            background=C["log_bg"], foreground=C["fg"],
            insertbackground=C["fg"],
            relief=tk.FLAT, wrap=tk.WORD,
            font=("Consolas", 10),
            selectbackground=C["sel"],
            padx=6, pady=4,
        )
        sb = ttk.Scrollbar(lf, command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.pack(fill=tk.BOTH, expand=True)

        self._log.tag_configure("timestamp",  foreground="#569cd6")
        self._log.tag_configure("sender",     foreground=C["accent"],
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("system",     foreground=C["system"],
                                font=("Consolas", 10, "italic"))
        self._log.tag_configure("error",      foreground=C["error"])
        self._log.tag_configure("caught_code",foreground=C["yellow"],
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("auto_ok",    foreground=C["ok"],
                                font=("Consolas", 10, "italic"))

        # ── 상태바 ─────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="대기 중")
        tk.Label(self, textvariable=self._status_var,
                 bg=C["panel"], fg=C["fg_dim"],
                 font=("Segoe UI", 8), anchor=tk.W,
                 padx=10, pady=4).pack(fill=tk.X, side=tk.BOTTOM)

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
            self._current_acct_var.set("등록된 계정 없음 — [계정 관리]에서 추가하세요")
        else:
            enabled = [a for a in self._accounts if a.get("enabled", True)]
            total = len(self._accounts)
            self._current_acct_var.set(
                f"총 {total}개 계정 등록 | 활성 {len(enabled)}개")

    def _open_account_manager(self) -> None:
        def on_save(accounts, current_idx):
            self._accounts = accounts
            self._account_idx = current_idx
            self._update_current_acct_label()
            save_config(self._get_current_config())

        AccountManagerDialog(self, self._accounts, self._account_idx, on_save)

    def _advance_account(self) -> None:
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
        self._status_var.set(f"모니터링 중  |  채팅방: {room_name}")
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

        if (self._monitor_thread is not None
                and not self._monitor_thread.is_alive()
                and self._stop_btn["state"] == tk.NORMAL):
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_var.set("모니터링 종료")
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
        self._history_var.set("  ".join(self._caught_history) if self._caught_history else "없음")
        self._status_var.set(f"코드 캐치: {code}  ({ts} / {sender})")

        if not SELENIUM_OK:
            self._append_log("⚠ selenium 미설치 — 자동 입력 불가", tag="error")
            return
        if not self._auto_var.get():
            self._append_log("ℹ 자동 입력 비활성", tag="system")
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
        if self._auto_cancel_event.is_set():
            return

        accounts = [a for a in self._accounts if a.get("enabled", True)]
        if not accounts:
            self._msg_queue.put(("error", "⚠ 활성화된 계정이 없습니다. 계정 관리에서 ☑ 체크하세요."))
            return

        total = len(accounts)
        self._msg_queue.put(("system", f"━━ 자동 입력 시작: {code} | 활성 계정 {total}개 순차 처리 ━━"))

        success_count = 0
        fail_count = 0

        for i, acct in enumerate(accounts):
            if self._auto_cancel_event.is_set():
                self._msg_queue.put(("system", "── 자동 입력 취소됨 ──"))
                return

            acct_label = f"[{i+1}/{total}] {acct['email']}"
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

        tag = "auto_ok" if fail_count == 0 else "system"
        self._msg_queue.put((
            tag,
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
    def __init__(self, parent, account: dict = None) -> None:
        super().__init__(parent)
        self.title("계정 추가" if account is None else "계정 수정")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.grab_set()
        self.result: Optional[dict] = None
        self.columnconfigure(1, weight=1)

        fields = [
            ("이메일",   "email",    False),
            ("비밀번호", "password", True),
            ("비고",     "memo",     False),
        ]
        self._vars = {}
        for r, (label, key, is_pw) in enumerate(fields):
            ttk.Label(self, text=f"{label}:", style="TLabel").grid(
                row=r, column=0, padx=14, pady=6, sticky=tk.W)
            var = tk.StringVar(value=account.get(key, "") if account else "")
            self._vars[key] = var
            entry = ttk.Entry(self, textvariable=var, width=34,
                              show="*" if is_pw else "")
            entry.grid(row=r, column=1, padx=(0, 14), pady=6, sticky=tk.EW)
            if is_pw:
                self._pw_entry = entry

        # 비밀번호 표시 체크
        self._show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="비밀번호 표시", variable=self._show_pw,
                        command=lambda: self._pw_entry.config(
                            show="" if self._show_pw.get() else "*")).grid(
            row=1, column=2, padx=(0, 14))

        # 사용 여부
        self._enabled_var = tk.BooleanVar(
            value=account.get("enabled", True) if account else True)
        ttk.Checkbutton(self, text="이 계정 사용",
                        variable=self._enabled_var).grid(
            row=3, column=1, sticky=tk.W, padx=(0, 14), pady=(0, 6))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=12)
        ttk.Button(btn_frame, text="확인", style="Start.TButton",
                   command=self._ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="취소",
                   command=self.destroy).pack(side=tk.LEFT, padx=6)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _ok(self) -> None:
        email = self._vars["email"].get().strip()
        if not email:
            messagebox.showwarning("입력 오류", "이메일을 입력하세요.", parent=self)
            return
        self.result = {
            "email":    email,
            "password": self._vars["password"].get(),
            "memo":     self._vars["memo"].get().strip(),
            "enabled":  self._enabled_var.get(),
        }
        self.destroy()


class AccountManagerDialog(tk.Toplevel):
    def __init__(self, parent, accounts: list, current_idx: int, on_save) -> None:
        super().__init__(parent)
        self.title("계정 목록 관리")
        self.resizable(True, True)
        self.minsize(580, 460)
        self.configure(bg=C["bg"])
        self.grab_set()

        self._accounts: list = list(accounts)
        self._current_idx: int = current_idx
        self._on_save = on_save

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        ttk.Label(self,
                  text="  ☑ 클릭 → 사용/미사용 전환    ✕ 클릭 → 삭제    더블클릭 → 수정",
                  foreground=C["fg_dim"],
                  font=("Segoe UI", 8)).pack(padx=10, pady=(8, 2), anchor=tk.W)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        cols = ("check", "no", "email", "password", "memo", "del")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", height=16)
        self._tree.heading("check",    text="사용")
        self._tree.heading("no",       text="No.")
        self._tree.heading("email",    text="이메일")
        self._tree.heading("password", text="비밀번호")
        self._tree.heading("memo",     text="비고")
        self._tree.heading("del",      text="삭제")
        self._tree.column("check",    width=45,  anchor="center", stretch=False)
        self._tree.column("no",       width=45,  anchor="center", stretch=False)
        self._tree.column("email",    width=200)
        self._tree.column("password", width=80,  stretch=False)
        self._tree.column("memo",     width=130)
        self._tree.column("del",      width=45,  anchor="center", stretch=False)

        sb = ttk.Scrollbar(tree_frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.bind("<Double-1>",      self._on_double_click)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self._tree.tag_configure("current",  foreground=C["accent"])
        self._tree.tag_configure("disabled", foreground="#555555")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=10, pady=(4, 10))

        ttk.Button(btn_frame, text="추가",
                   command=self._add).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="수정",
                   command=self._edit).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="전체 선택",
                   command=self._enable_all).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="전체 해제",
                   command=self._disable_all).pack(side=tk.LEFT, padx=3)
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(btn_frame, text="저장 후 닫기", style="Start.TButton",
                   command=self._save_close).pack(side=tk.LEFT, padx=3)

    def _refresh_list(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, acct in enumerate(self._accounts):
            enabled = acct.get("enabled", True)
            check  = "☑" if enabled else "☐"
            marker = "▶" if i == self._current_idx else str(i + 1)
            masked = "•" * min(len(acct.get("password", "")), 8) or "(없음)"
            memo   = acct.get("memo", "")
            tags = []
            if i == self._current_idx:
                tags.append("current")
            if not enabled:
                tags.append("disabled")
            self._tree.insert("", tk.END, iid=str(i),
                              values=(check, marker, acct.get("email", ""),
                                      masked, memo, "✕"),
                              tags=tuple(tags))
        if self._accounts and 0 <= self._current_idx < len(self._accounts):
            self._tree.selection_set(str(self._current_idx))
            self._tree.see(str(self._current_idx))

    def _on_tree_click(self, event) -> None:
        if self._tree.identify_region(event.x, event.y) != "cell":
            return
        col    = self._tree.identify_column(event.x)
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        idx = int(row_id)
        if col == "#1":
            self._toggle_enabled(idx)
        elif col == "#6":
            self._delete_by_idx(idx)

    def _on_double_click(self, event) -> None:
        if self._tree.identify_column(event.x) in ("#1", "#6"):
            return
        self._edit()

    def _toggle_enabled(self, idx: int) -> None:
        self._accounts[idx]["enabled"] = not self._accounts[idx].get("enabled", True)
        self._refresh_list()

    def _delete_by_idx(self, idx: int) -> None:
        if not messagebox.askyesno(
                "삭제 확인",
                f"계정 {idx+1} ({self._accounts[idx]['email']})을 삭제하시겠습니까?",
                parent=self):
            return
        self._accounts.pop(idx)
        if self._current_idx >= len(self._accounts):
            self._current_idx = max(0, len(self._accounts) - 1)
        self._refresh_list()

    def _enable_all(self) -> None:
        for a in self._accounts:
            a["enabled"] = True
        self._refresh_list()

    def _disable_all(self) -> None:
        for a in self._accounts:
            a["enabled"] = False
        self._refresh_list()

    def _selected_idx(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self) -> None:
        if len(self._accounts) >= 50:
            messagebox.showwarning("최대 50개", "계정은 최대 50개까지 등록 가능합니다.", parent=self)
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

    def _save_close(self) -> None:
        self._on_save(self._accounts, self._current_idx)
        self.destroy()


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
