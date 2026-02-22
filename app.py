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

CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_CONFIG = {"room_name": "", "poll_interval": 3, "watch_sender": ""}

# 영문+숫자 8자리 정확히 일치
CODE_PATTERN = re.compile(r'^[A-Za-z0-9]{8}$')

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
        self.minsize(540, 600)

        # 상태
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._msg_queue: queue.Queue = queue.Queue()
        self._caught_history: list[str] = []  # 코드 히스토리

        cfg = load_config()
        self._build_ui(cfg)
        self._poll_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self, cfg: dict) -> None:
        # ── 설정 프레임 ──────────────────────────────────────────────
        setting_frame = ttk.LabelFrame(self, text="설정", padding=8)
        setting_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        setting_frame.columnconfigure(1, weight=1)

        ttk.Label(setting_frame, text="채팅방 이름:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self._room_var = tk.StringVar(value=cfg["room_name"])
        ttk.Entry(setting_frame, textvariable=self._room_var).grid(
            row=0, column=1, sticky=tk.EW, padx=(6, 0), pady=2
        )

        ttk.Label(setting_frame, text="폴링 간격:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        interval_frame = ttk.Frame(setting_frame)
        interval_frame.grid(row=1, column=1, sticky=tk.W, padx=(6, 0), pady=2)
        self._interval_var = tk.StringVar(value=str(cfg["poll_interval"]))
        ttk.Entry(interval_frame, textvariable=self._interval_var, width=6).pack(
            side=tk.LEFT
        )
        ttk.Label(interval_frame, text="초").pack(side=tk.LEFT, padx=4)

        ttk.Label(setting_frame, text="발신자 필터:").grid(
            row=2, column=0, sticky=tk.W, pady=2
        )
        self._sender_var = tk.StringVar(value=cfg["watch_sender"])
        ttk.Entry(setting_frame, textvariable=self._sender_var).grid(
            row=2, column=1, sticky=tk.EW, padx=(6, 0), pady=2
        )
        ttk.Label(setting_frame, text="(비워두면 전체)", foreground="gray").grid(
            row=2, column=2, sticky=tk.W, padx=4
        )

        self._topmost_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            setting_frame,
            text="항상 위",
            variable=self._topmost_var,
            command=self._toggle_topmost,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        # ── 제어 버튼 ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=4)

        self._start_btn = ttk.Button(
            btn_frame, text="▶ 모니터링 시작", command=self._start_monitor
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 4))

        self._stop_btn = ttk.Button(
            btn_frame, text="■ 중지", command=self._stop_monitor, state=tk.DISABLED
        )
        self._stop_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_frame, text="로그 지우기", command=self._clear_log).pack(
            side=tk.LEFT, padx=4
        )

        # ── 캐치 패널 ─────────────────────────────────────────────────
        catch_frame = ttk.LabelFrame(self, text="캐치된 코드  (영숫자 8자리)", padding=8)
        catch_frame.pack(fill=tk.X, padx=10, pady=4)

        # 최신 코드 — 크게 표시
        code_box = tk.Frame(catch_frame, bg="#0d1117", relief=tk.FLAT, bd=1)
        code_box.pack(fill=tk.X, pady=(0, 6))

        self._latest_code_var = tk.StringVar(value="—")
        tk.Label(
            code_box,
            textvariable=self._latest_code_var,
            font=("Consolas", 36, "bold"),
            fg="#f0c040",
            bg="#0d1117",
            pady=12,
        ).pack()

        self._latest_meta_var = tk.StringVar(value="대기 중...")
        tk.Label(
            code_box,
            textvariable=self._latest_meta_var,
            font=("Consolas", 9),
            fg="#8b949e",
            bg="#0d1117",
            pady=2,
        ).pack()

        # 히스토리 — 작게 한 줄
        hist_frame = tk.Frame(catch_frame, bg=self.cget("bg"))
        hist_frame.pack(fill=tk.X)
        tk.Label(hist_frame, text="이전:", font=("Consolas", 9), fg="gray").pack(
            side=tk.LEFT
        )
        self._history_var = tk.StringVar(value="없음")
        tk.Label(
            hist_frame,
            textvariable=self._history_var,
            font=("Consolas", 9),
            fg="#4ec9b0",
        ).pack(side=tk.LEFT, padx=4)

        # ── 전체 메시지 로그 ──────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="전체 메시지 로그", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._log = tk.Text(
            log_frame,
            state=tk.DISABLED,
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 10),
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.pack(fill=tk.BOTH, expand=True)

        # 로그 컬러 태그
        self._log.tag_configure("timestamp", foreground="#569cd6")
        self._log.tag_configure("sender", foreground="#4ec9b0",
                                font=("Consolas", 10, "bold"))
        self._log.tag_configure("system", foreground="#6a9955",
                                font=("Consolas", 10, "italic"))
        self._log.tag_configure("error", foreground="#f44747")
        # 캐치된 메시지는 노란색 굵게 강조
        self._log.tag_configure("caught_code", foreground="#f0c040",
                                font=("Consolas", 10, "bold"))

        # ── 상태바 ────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="대기 중")
        ttk.Label(
            self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W
        ).pack(fill=tk.X, padx=10, pady=(0, 6))

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

        save_config({
            "room_name": room_name,
            "poll_interval": poll_interval,
            "watch_sender": watch_sender,
        })

        self._stop_event = threading.Event()
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

        # 로그에 항상 출력 (캐치된 코드는 노란색 강조)
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

        # 캐치 패널 업데이트
        if is_code:
            self._update_catch_panel(code, msg.timestamp_str, msg.sender)

    def _update_catch_panel(self, code: str, ts: str, sender: str) -> None:
        # 히스토리에 현재 최신값 밀어넣기
        current = self._latest_code_var.get()
        if current != "—":
            self._caught_history.insert(0, current)
            self._caught_history = self._caught_history[:8]  # 최대 8개 보관

        # 최신 코드 표시
        self._latest_code_var.set(code)
        self._latest_meta_var.set(f"{ts}  |  {sender}")

        # 히스토리 한 줄 표시
        if self._caught_history:
            self._history_var.set("  ".join(self._caught_history))
        else:
            self._history_var.set("없음")

        # 상태바에도 반영
        self._status_var.set(f"코드 캐치: {code}  ({ts} / {sender})")

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
