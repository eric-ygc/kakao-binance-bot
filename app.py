"""
카카오 메시지 모니터 — tkinter GUI 앱

실행: python app.py
설정: config.json (자동 저장/복원)
"""
import datetime
import json
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
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

CONFIG_PATH   = BASE_DIR / "config.json"
LOG_DATA_PATH = BASE_DIR / "log_data.json"
DEFAULT_CONFIG = {
    "room_name": "",
    "poll_interval": 3,
    "watch_sender": "",
    "auto_input": False,
    "chrome_port": 9222,
    "site_urls": ["https://dsj44.com/h5/#/login", "", "", "", "", "", "", "", "", ""],
    "accounts": [],
    "account_index": 0,
    "monitor_schedules": [
        {"enabled": False, "start": "", "stop": ""},
        {"enabled": False, "start": "", "stop": ""},
    ],
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
        self._caught_codes_full: list = []   # {"code","ts","sender","datetime"}
        self._log_lines: list = []            # {"text","tag"} — 최대 2000줄
        self._processed_codes: set = set()
        self._monitor_schedules: list = []   # [(enabled_var, start_var, stop_var), ...]
        self._last_sched_action: list = ["", ""]  # 중복 실행 방지

        cfg = load_config()
        self._accounts: list = list(cfg.get("accounts", []))
        self._account_idx: int = int(cfg.get("account_index", 0))
        if self._account_idx >= len(self._accounts):
            self._account_idx = 0

        self._apply_dark_theme()
        self._build_ui(cfg)
        self._load_log_data()
        self._start_monitor_scheduler()
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

    # ------------------------------------------------------------------
    # Bento Grid 카드 헬퍼
    # ------------------------------------------------------------------

    def _make_card(self, parent: tk.Widget, title: str = "") -> tk.Frame:
        """
        Bento Grid 카드 생성.
        outer(border) > inner(panel) > pad(패딩) 구조.
        타이틀이 있으면 pad 안에 label(pack) + body(pack) 로 분리하여
        body 안에서 grid/pack 을 자유롭게 사용할 수 있도록 한다.
        반환값(body)의 ._outer 속성으로 외부에서 grid 배치.
        """
        outer = tk.Frame(parent, bg=C["border"])
        inner = tk.Frame(outer, bg=C["panel"])
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        pad = tk.Frame(inner, bg=C["panel"])
        pad.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        if title:
            # 타이틀 라벨 (pack) 과 body (pack) 를 분리 → grid/pack 혼용 방지
            tk.Label(pad, text=title,
                     bg=C["panel"], fg=C["accent"],
                     font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 7))
            body = tk.Frame(pad, bg=C["panel"])
            body.pack(fill=tk.BOTH, expand=True)
        else:
            body = pad
        body._outer = outer
        return body

    # ------------------------------------------------------------------
    # UI 구성 — Bento Grid
    # ------------------------------------------------------------------

    def _build_ui(self, cfg: dict) -> None:
        G = 6   # card gap

        # ── 상태바 (하단 고정) ─────────────────────────────────────
        self._status_var = tk.StringVar(value="대기 중")
        tk.Label(self, textvariable=self._status_var,
                 bg=C["panel2"], fg=C["fg_dim"],
                 font=("Segoe UI", 8), anchor=tk.W,
                 padx=10, pady=3).pack(fill=tk.X, side=tk.BOTTOM)

        # ── Bento 그리드 컨테이너 ──────────────────────────────────
        bento = tk.Frame(self, bg=C["bg"])
        bento.pack(fill=tk.BOTH, expand=True, padx=G, pady=G)

        # col 0: 코드 카드 (고정폭)  /  col 1: 나머지 (확장)
        bento.columnconfigure(0, weight=0, minsize=232)
        bento.columnconfigure(1, weight=1)
        # row 3: 로그 카드만 세로 확장
        bento.rowconfigure(3, weight=1)

        # ╔══════════════════════════════════════╗
        # ║  A: 캐치된 코드  (col 0, row 0–1)   ║
        # ╚══════════════════════════════════════╝
        ca = self._make_card(bento)
        ca._outer.grid(row=0, column=0, rowspan=2, sticky="nsew",
                       padx=(0, G), pady=(0, G))

        tk.Label(ca, text="캐치된 코드",
                 bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, pady=(0, 6))

        code_box = tk.Frame(ca, bg=C["code_bg"],
                            highlightbackground=C["border"],
                            highlightthickness=1)
        code_box.pack(fill=tk.X)

        self._latest_code_var = tk.StringVar(value="—")
        tk.Label(code_box, textvariable=self._latest_code_var,
                 font=("Consolas", 34, "bold"),
                 fg=C["yellow"], bg=C["code_bg"], pady=10).pack()

        self._latest_meta_var = tk.StringVar(value="대기 중...")
        tk.Label(code_box, textvariable=self._latest_meta_var,
                 font=("Segoe UI", 8), fg=C["fg_dim"],
                 bg=C["code_bg"], pady=3).pack()

        tk.Frame(ca, bg=C["border"], height=1).pack(fill=tk.X, pady=(10, 5))

        hist_row = tk.Frame(ca, bg=C["panel"])
        hist_row.pack(fill=tk.X)
        tk.Label(hist_row, text="이전:", font=("Segoe UI", 8),
                 fg=C["fg_dim"], bg=C["panel"]).pack(side=tk.LEFT)
        self._history_var = tk.StringVar(value="없음")
        tk.Label(hist_row, textvariable=self._history_var,
                 font=("Consolas", 8), fg=C["accent"], bg=C["panel"],
                 wraplength=190, justify=tk.LEFT).pack(side=tk.LEFT, padx=4)

        # ╔══════════════════════════════════════╗
        # ║  B: 모니터링 설정  (col 1, row 0)   ║
        # ╚══════════════════════════════════════╝
        cb = self._make_card(bento, "모니터링 설정")
        cb._outer.grid(row=0, column=1, sticky="nsew", pady=(0, G))
        cb.columnconfigure(1, weight=1)

        ttk.Label(cb, text="채팅방 이름", style="Panel.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=3)
        self._room_var = tk.StringVar(value=cfg["room_name"])
        ttk.Entry(cb, textvariable=self._room_var).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=3)

        ttk.Label(cb, text="폴링 간격", style="Panel.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=3)
        ivf = ttk.Frame(cb, style="Panel.TFrame")
        ivf.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=3)
        self._interval_var = tk.StringVar(value=str(cfg["poll_interval"]))
        ttk.Entry(ivf, textvariable=self._interval_var, width=6).pack(side=tk.LEFT)
        ttk.Label(ivf, text=" 초", style="Panel.TLabel").pack(side=tk.LEFT)

        ttk.Label(cb, text="발신자 필터", style="Panel.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=3)
        self._sender_var = tk.StringVar(value=cfg["watch_sender"])
        ttk.Entry(cb, textvariable=self._sender_var).grid(
            row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=3)
        ttk.Label(cb, text="비워두면 전체", style="Dim.TLabel").grid(
            row=2, column=2, sticky=tk.W, padx=6)

        self._topmost_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cb, text="항상 위 표시",
                        variable=self._topmost_var,
                        command=self._toggle_topmost).grid(
            row=3, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))

        # ╔══════════════════════════════════════╗
        # ║  C: 제어 버튼  (col 1, row 1)       ║
        # ╚══════════════════════════════════════╝
        cc = self._make_card(bento)
        cc._outer.grid(row=1, column=1, sticky="nsew", pady=(0, G))

        bf = tk.Frame(cc, bg=C["panel"])
        bf.pack(fill=tk.X)

        self._start_btn = ttk.Button(bf, text="▶  모니터링 시작",
                                     style="Start.TButton",
                                     command=self._start_monitor)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._stop_btn = ttk.Button(bf, text="■  중지",
                                    style="Stop.TButton",
                                    command=self._stop_monitor,
                                    state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Separator(bf, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=(0, 8), pady=2)

        ttk.Button(bf, text="로그 지우기",
                   command=self._clear_log).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bf, text="텍스트 저장",
                   command=self._export_text).pack(side=tk.LEFT)

        # 예약 시작·종료
        tk.Frame(cc, bg=C["border"], height=1).pack(fill=tk.X, pady=(10, 6))
        tk.Label(cc, text="예약 시작·종료 시각  (HH:MM)",
                 font=("Segoe UI", 8), fg=C["fg_dim"],
                 bg=C["panel"]).pack(anchor=tk.W, pady=(0, 3))

        saved_scheds = cfg.get("monitor_schedules", DEFAULT_CONFIG["monitor_schedules"])
        while len(saved_scheds) < 2:
            saved_scheds.append({"enabled": False, "start": "", "stop": ""})

        for i, sc in enumerate(saved_scheds[:2]):
            ev  = tk.BooleanVar(value=bool(sc.get("enabled", False)))
            sv  = tk.StringVar(value=str(sc.get("start", "")))
            stv = tk.StringVar(value=str(sc.get("stop", "")))
            self._monitor_schedules.append((ev, sv, stv))

            row = tk.Frame(cc, bg=C["panel"])
            row.pack(fill=tk.X, pady=1)
            ttk.Checkbutton(row, variable=ev, style="TCheckbutton").pack(side=tk.LEFT)
            tk.Label(row, text="시작", font=("Segoe UI", 8),
                     fg=C["fg_dim"], bg=C["panel"]).pack(side=tk.LEFT, padx=(2, 2))
            tk.Entry(row, textvariable=sv,
                     font=("Consolas", 10), fg=C["ok"], bg=C["input"],
                     insertbackground=C["ok"], relief=tk.FLAT,
                     justify=tk.CENTER, width=6).pack(side=tk.LEFT)
            tk.Label(row, text="  종료", font=("Segoe UI", 8),
                     fg=C["fg_dim"], bg=C["panel"]).pack(side=tk.LEFT, padx=(6, 2))
            tk.Entry(row, textvariable=stv,
                     font=("Consolas", 10), fg=C["error"], bg=C["input"],
                     insertbackground=C["error"], relief=tk.FLAT,
                     justify=tk.CENTER, width=6).pack(side=tk.LEFT)

        # ╔══════════════════════════════════════╗
        # ║  D: 자동 입력 설정  (full, row 2)   ║
        # ╚══════════════════════════════════════╝
        cd = self._make_card(bento, "자동 입력 설정")
        cd._outer.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, G))
        cd.columnconfigure(1, weight=1)
        cd.columnconfigure(3, weight=1)

        self._auto_var = tk.BooleanVar(value=cfg.get("auto_input", False))
        auto_chk = ttk.Checkbutton(cd, text="코드 캐치 시 자동으로 사이트에 입력",
                                   variable=self._auto_var)
        auto_chk.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 6))

        if not SELENIUM_OK:
            ttk.Label(cd, text="⚠  selenium 미설치 — 자동 입력 불가",
                      foreground=C["error"],
                      style="Panel.TLabel").grid(
                row=0, column=4, sticky=tk.W, padx=(16, 0))
            self._auto_var.set(False)
            auto_chk.config(state=tk.DISABLED)

        # 사이트 URL — 5개를 2열 배치
        saved_urls = cfg.get("site_urls", DEFAULT_CONFIG["site_urls"])
        if isinstance(saved_urls, str):
            saved_urls = [saved_urls] + [""] * 9
        while len(saved_urls) < 10:
            saved_urls.append("")
        self._site_url_vars = [tk.StringVar(value=saved_urls[i]) for i in range(10)]

        for pr, (li, ri) in enumerate([(0,1),(2,3),(4,5),(6,7),(8,9)], start=1):
            ttk.Label(cd, text=f"사이트 {li+1}", style="Panel.TLabel").grid(
                row=pr, column=0, sticky=tk.W, pady=2)
            ttk.Entry(cd, textvariable=self._site_url_vars[li]).grid(
                row=pr, column=1, sticky=tk.EW, padx=(6, 14), pady=2)
            ttk.Label(cd, text=f"사이트 {ri+1}", style="Panel.TLabel").grid(
                row=pr, column=2, sticky=tk.W, pady=2)
            ttk.Entry(cd, textvariable=self._site_url_vars[ri]).grid(
                row=pr, column=3, sticky=tk.EW, padx=(6, 0), pady=2)

        # Chrome 포트 + 접속 테스트
        ttk.Label(cd, text="Chrome 포트", style="Panel.TLabel").grid(
            row=6, column=0, sticky=tk.W, pady=(6, 2))
        pf = ttk.Frame(cd, style="Panel.TFrame")
        pf.grid(row=6, column=1, sticky=tk.W, padx=(6, 14), pady=(6, 2))
        self._port_var = tk.StringVar(value=str(cfg.get("chrome_port", 9222)))
        ttk.Entry(pf, textvariable=self._port_var, width=7).pack(side=tk.LEFT)
        ttk.Label(pf, text="  기본 9222", style="Dim.TLabel").pack(side=tk.LEFT)
        ttk.Button(cd, text="접속 테스트", command=self._test_connections).grid(
            row=6, column=2, columnspan=2, sticky=tk.EW, padx=(6, 0), pady=(6, 2))

        # 현재 계정
        ttk.Label(cd, text="현재 계정", style="Panel.TLabel").grid(
            row=7, column=0, sticky=tk.W, pady=(8, 2))
        self._current_acct_var = tk.StringVar()
        ttk.Label(cd, textvariable=self._current_acct_var,
                  style="Panel.TLabel",
                  foreground=C["accent"]).grid(
            row=7, column=1, columnspan=2, sticky=tk.W, padx=(6, 0), pady=(8, 2))
        ttk.Button(cd, text="계정 관리",
                   command=self._open_account_manager).grid(
            row=7, column=3, sticky=tk.E, pady=(8, 2))
        self._update_current_acct_label()

        # ╔══════════════════════════════════════╗
        # ║  E: 메시지 로그  (full, row 3, 확장) ║
        # ╚══════════════════════════════════════╝
        ce = self._make_card(bento, "메시지 로그")
        ce._outer.grid(row=3, column=0, columnspan=2, sticky="nsew")
        ce.columnconfigure(0, weight=1)
        ce.rowconfigure(0, weight=1)

        log_frame = tk.Frame(ce, bg=C["log_bg"])
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self._log = tk.Text(
            log_frame, state=tk.DISABLED,
            background=C["log_bg"], foreground=C["fg"],
            insertbackground=C["fg"],
            relief=tk.FLAT, wrap=tk.WORD,
            font=("Consolas", 10),
            selectbackground=C["sel"],
            padx=6, pady=4,
        )
        sb = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        self._log.grid(row=0, column=0, sticky="nsew")

        self._log.tag_configure("timestamp",   foreground="#569cd6")
        self._log.tag_configure("sender",      foreground=C["accent"],
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("system",      foreground=C["system"],
                                font=("Consolas", 10, "italic"))
        self._log.tag_configure("error",       foreground=C["error"])
        self._log.tag_configure("caught_code", foreground=C["yellow"],
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("auto_ok",     foreground=C["ok"],
                                font=("Consolas", 10, "italic"))

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
            "monitor_schedules": [
                {"enabled": bool(ev.get()),
                 "start": sv.get().strip(),
                 "stop": stv.get().strip()}
                for ev, sv, stv in self._monitor_schedules
            ],
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

    def _test_connections(self) -> None:
        """입력된 사이트 URL 접속 가능 여부를 백그라운드 스레드에서 테스트."""
        import urllib.request
        urls = [v.get().strip() for v in self._site_url_vars if v.get().strip()]
        if not urls:
            messagebox.showinfo("접속 테스트", "입력된 사이트 URL이 없습니다.")
            return

        def _run():
            lines = []
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8):
                        lines.append(f"✓  {url}")
                except Exception as e:
                    lines.append(f"✗  {url}\n     {e}")
            self.after(0, lambda m="\n\n".join(lines): messagebox.showinfo("접속 테스트 결과", m))

        messagebox.showinfo("접속 테스트", f"{len(urls)}개 사이트 접속 테스트 중...\n완료되면 결과 팝업이 표시됩니다.")
        threading.Thread(target=_run, daemon=True).start()

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

    # ------------------------------------------------------------------
    # 예약 시작·종료 스케줄러
    # ------------------------------------------------------------------

    def _start_monitor_scheduler(self) -> None:
        self._last_sched_action = ["", ""]
        self._check_monitor_schedule()

    def _check_monitor_schedule(self) -> None:
        now = datetime.datetime.now().strftime("%H:%M")
        is_running = (self._stop_event is not None and
                      not self._stop_event.is_set())

        for i, (ev, sv, stv) in enumerate(self._monitor_schedules):
            if not ev.get():
                continue
            start_t = sv.get().strip()
            stop_t  = stv.get().strip()

            if start_t and start_t == now and not is_running:
                key = f"start-{now}-{i}"
                if self._last_sched_action[i] != key:
                    self._last_sched_action[i] = key
                    self._append_log(f"⏰ 예약 시작: {now}", tag="system")
                    self._start_monitor()
                    is_running = True

            if stop_t and stop_t == now and is_running:
                key = f"stop-{now}-{i}"
                if self._last_sched_action[i] != key:
                    self._last_sched_action[i] = key
                    self._append_log(f"⏰ 예약 종료: {now}", tag="system")
                    self._stop_monitor()
                    is_running = False

        self.after(10000, self._check_monitor_schedule)

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.config(state=tk.DISABLED)

    def _toggle_topmost(self) -> None:
        self.attributes("-topmost", self._topmost_var.get())

    def _on_close(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        self._save_log_data()
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

        # 로그 영구 저장용 plain 라인
        if is_code:
            plain = f"[{msg.timestamp_str}] {msg.sender}: {code}  ★"
            self._log_lines.append({"text": plain, "tag": "caught_code"})
        else:
            plain = f"[{msg.timestamp_str}] {msg.sender}: {msg.content}"
            self._log_lines.append({"text": plain, "tag": ""})
        if len(self._log_lines) > 2000:
            self._log_lines = self._log_lines[-2000:]

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
        self._caught_codes_full.append({
            "code": code, "ts": ts, "sender": sender,
            "datetime": datetime.datetime.now().isoformat(timespec="seconds"),
        })
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
        self._log_lines.append({"text": text, "tag": tag})
        if len(self._log_lines) > 2000:
            self._log_lines = self._log_lines[-2000:]
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, text + "\n", tag if tag else ())
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # 로그 영구 저장 / 복원 / 내보내기
    # ------------------------------------------------------------------

    def _load_log_data(self) -> None:
        """프로그램 시작 시 log_data.json에서 이전 로그와 캐치 코드 복원."""
        if not LOG_DATA_PATH.exists():
            return
        try:
            with open(LOG_DATA_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # 로그 라인 복원
        lines = data.get("log_lines", [])
        self._log_lines = lines[-2000:]
        if self._log_lines:
            self._log.config(state=tk.NORMAL)
            for item in self._log_lines:
                tag = item.get("tag", "")
                self._log.insert(tk.END, item.get("text", "") + "\n",
                                 tag if tag else ())
            self._log.see(tk.END)
            self._log.config(state=tk.DISABLED)

        # 캐치 코드 복원
        caught = data.get("caught_codes", [])
        self._caught_codes_full = caught
        if caught:
            latest = caught[-1]
            self._latest_code_var.set(latest["code"])
            self._latest_meta_var.set(f"{latest['ts']}  |  {latest['sender']}")
            prev = [c["code"] for c in reversed(caught[:-1])][:8]
            self._caught_history = prev
            self._history_var.set("  ".join(prev) if prev else "없음")
            self._status_var.set(
                f"이전 코드 복원: {latest['code']}  ({latest.get('datetime','')[:10]})")

    def _save_log_data(self) -> None:
        """종료 시 log_data.json에 로그·캐치 코드 저장."""
        try:
            data = {
                "caught_codes": self._caught_codes_full,
                "log_lines":    self._log_lines[-2000:],
            }
            with open(LOG_DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"로그 데이터 저장 실패: {e}")

    def _export_text(self) -> None:
        """캐치 코드 + 메시지 로그를 텍스트 파일로 내보내기."""
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
            initialfile=f"카카오모니터_{now_str}.txt",
            title="텍스트 파일로 저장",
        )
        if not path:
            return

        sep = "═" * 60
        out = []

        # ── 캐치된 코드 목록
        out.append(sep)
        out.append(f"  캐치된 코드 목록  (총 {len(self._caught_codes_full)}개)")
        out.append(sep)
        if self._caught_codes_full:
            for i, c in enumerate(self._caught_codes_full, 1):
                dt = c.get("datetime", "")[:19].replace("T", " ")
                out.append(f"  {i:>3}.  {c['code']}   {c['ts']}   {c['sender']}   {dt}")
        else:
            out.append("  (없음)")
        out.append("")

        # ── 메시지 로그
        out.append(sep)
        out.append("  메시지 로그")
        out.append(sep)
        for item in self._log_lines:
            out.append(item.get("text", ""))

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(out))
            self._append_log(f"✓ 저장 완료: {path}", tag="auto_ok")
        except Exception as e:
            messagebox.showerror("저장 실패", str(e), parent=self)


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
        ttk.Button(btn_frame, text="엑셀 불러오기",
                   command=self._import_excel).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="엑셀 저장",
                   command=self._export_excel).pack(side=tk.LEFT, padx=3)
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

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Excel 파일", "*.xlsx *.xls"), ("모든 파일", "*.*")],
            title="계정 목록 엑셀 파일 선택",
            parent=self,
        )
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            messagebox.showerror("불러오기 실패", str(e), parent=self)
            return

        if not rows:
            messagebox.showwarning("내용 없음", "엑셀 파일이 비어 있습니다.", parent=self)
            return

        # 헤더 행 스킵
        start = 0
        first = str(rows[0][0] or "").strip().lower()
        if first in ("이메일", "email", "e-mail"):
            start = 1

        new_accounts = []
        for row in rows[start:]:
            if not row or not row[0]:
                continue
            email = str(row[0]).strip()
            if not email:
                continue
            pw    = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            memo  = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
            enabled_raw = str(row[3]).strip().lower() if len(row) > 3 and row[3] is not None else "true"
            enabled = enabled_raw not in ("false", "x", "✕", "0", "n", "no", "미사용")
            new_accounts.append({"email": email, "password": pw,
                                  "memo": memo, "enabled": enabled})

        if not new_accounts:
            messagebox.showwarning("계정 없음", "불러올 계정이 없습니다.", parent=self)
            return

        mode = messagebox.askyesnocancel(
            "불러오기 방식",
            f"엑셀에서 계정 {len(new_accounts)}개를 찾았습니다.\n\n"
            "[예] 기존 목록에 추가\n"
            "[아니오] 기존 목록을 대체\n"
            "[취소] 취소",
            parent=self,
        )
        if mode is None:
            return
        if mode:
            self._accounts.extend(new_accounts)
        else:
            self._accounts = new_accounts
            self._current_idx = 0
        self._refresh_list()
        messagebox.showinfo("완료", f"계정 {len(new_accounts)}개를 불러왔습니다.", parent=self)

    def _export_excel(self) -> None:
        if not self._accounts:
            messagebox.showwarning("계정 없음", "내보낼 계정이 없습니다.", parent=self)
            return
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 파일", "*.xlsx"), ("모든 파일", "*.*")],
            initialfile=f"카카오모니터_계정_{now_str}.xlsx",
            title="계정 목록 저장",
            parent=self,
        )
        if not path:
            return
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "계정목록"

            headers = ["이메일", "비밀번호", "비고", "사용여부"]
            header_fill = PatternFill("solid", fgColor="2D6A2D")
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=h)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            for r, acct in enumerate(self._accounts, 2):
                ws.cell(row=r, column=1, value=acct.get("email", ""))
                ws.cell(row=r, column=2, value=acct.get("password", ""))
                ws.cell(row=r, column=3, value=acct.get("memo", ""))
                ws.cell(row=r, column=4, value="사용" if acct.get("enabled", True) else "미사용")

            ws.column_dimensions["A"].width = 32
            ws.column_dimensions["B"].width = 20
            ws.column_dimensions["C"].width = 20
            ws.column_dimensions["D"].width = 10
            wb.save(path)
        except Exception as e:
            messagebox.showerror("저장 실패", str(e), parent=self)
            return
        messagebox.showinfo("완료", f"계정 {len(self._accounts)}개를 저장했습니다.\n{path}", parent=self)

    def _save_close(self) -> None:
        self._on_save(self._accounts, self._current_idx)
        self.destroy()


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
