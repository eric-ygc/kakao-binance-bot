"""
카카오 매매봇 — 카카오모니터 + 보너스픽 통합 앱
"""
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR))

from app import App
from bonus_pick import BonusPickApp

NEU_BG    = "#1e2130"
NEU_DARK  = "#13151f"
NEU_LIGHT = "#2a2f47"


class MainApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("픽보조")
        self.resizable(True, True)
        self.minsize(560, 680)
        self.configure(bg=NEU_BG)

        # Notebook 탭 스타일
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",
            background=NEU_BG,
            borderwidth=0,
            tabmargins=[4, 4, 0, 0],
        )
        s.configure("TNotebook.Tab",
            background=NEU_BG,
            foreground="#6b7280",
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
            borderwidth=3,
            lightcolor=NEU_LIGHT,
            darkcolor=NEU_DARK,
        )
        s.map("TNotebook.Tab",
            background=[("selected", NEU_BG)],
            foreground=[("selected", "#5b86e5")],
            lightcolor=[("selected", NEU_LIGHT)],
            darkcolor=[("selected", NEU_DARK)],
        )

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        tab1 = tk.Frame(nb, bg=NEU_BG)
        tab2 = tk.Frame(nb, bg=NEU_BG)
        nb.add(tab1, text="  고정픽  ")
        nb.add(tab2, text="  보너스픽  ")

        # 사이트 URL 공유 변수 — 고정픽 config.json 기준으로 초기값 로드
        shared_urls = self._load_shared_site_urls()

        self._app = App(tab1, shared_site_url_vars=shared_urls)
        self._app.pack(fill=tk.BOTH, expand=True)

        self._bonus = BonusPickApp(tab2, shared_site_url_vars=shared_urls)
        self._bonus.pack(fill=tk.BOTH, expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_shared_site_urls(self) -> list:
        """고정픽 config.json에서 사이트 URL을 읽어 공유 StringVar 10개 반환."""
        try:
            cfg_path = BASE_DIR / "config.json"
            with open(cfg_path, encoding="utf-8") as f:
                data = json.load(f)
            urls = data.get("site_urls", [])
        except Exception:
            urls = []
        while len(urls) < 10:
            urls.append("")
        return [tk.StringVar(value=urls[i]) for i in range(10)]

    def _on_close(self) -> None:
        self._app._on_close()
        self._bonus._on_close()
        self.destroy()


if __name__ == "__main__":
    MainApp().mainloop()
