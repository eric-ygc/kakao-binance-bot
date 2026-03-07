"""
카카오 매매봇 — 카카오모니터 + 보너스픽 통합 앱
"""
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

NEU_BG    = "#e0e5ec"
NEU_DARK  = "#a3b1c6"
NEU_LIGHT = "#ffffff"


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
            foreground="#4a5568",
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
            borderwidth=3,
            lightcolor=NEU_LIGHT,
            darkcolor=NEU_DARK,
        )
        s.map("TNotebook.Tab",
            background=[("selected", NEU_BG)],
            foreground=[("selected", "#2a9d8f")],
            lightcolor=[("selected", NEU_LIGHT)],
            darkcolor=[("selected", NEU_DARK)],
        )

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        tab1 = tk.Frame(nb, bg=NEU_BG)
        tab2 = tk.Frame(nb, bg=NEU_BG)
        nb.add(tab1, text="  고정픽  ")
        nb.add(tab2, text="  보너스픽  ")

        self._app = App(tab1)
        self._app.pack(fill=tk.BOTH, expand=True)

        self._bonus = BonusPickApp(tab2)
        self._bonus.pack(fill=tk.BOTH, expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        self._app._on_close()
        self._bonus._on_close()
        self.destroy()


if __name__ == "__main__":
    MainApp().mainloop()
