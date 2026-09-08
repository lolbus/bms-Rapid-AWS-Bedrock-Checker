"""Bedrock Cost Checker - Tkinter app entry point."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import __version__
from . import config as config_mod
from . import creds as creds_mod
from . import pricing, theme
from .tabs.tab_cloudwatch import CloudWatchTab
from .tabs.tab_cost_explorer import CostExplorerTab
from .tabs.tab_calibrated import CalibratedTab
from .tabs.tab_discovery import DiscoveryTab
from .tabs.tab_settings import SettingsTab
from .theme import BM, FONT_MONO, FONT_SUB


def _asset(name: str) -> Path:
    """Bundled asset path. Frozen onedir: sys._MEIPASS is the _internal dir."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "bedrock_checker" / "assets" / name
    return Path(__file__).parent / "assets" / name


class App:
    def __init__(self):
        self.cfg_error = None
        try:
            self.cfg = config_mod.load_config()
        except config_mod.ConfigError as exc:
            self.cfg = dict(config_mod.DEFAULTS)
            self.cfg_error = str(exc)
        pricing.apply_overrides(self.cfg.get("pricing_overrides") or {})

        self.root = tk.Tk()
        self.root.title(f"Bedrock Cost Checker v{__version__} - A Buildman Shipped Project")
        self.root.geometry("1180x840")
        self.root.minsize(1000, 720)
        theme.apply(self.root)

        self._build_header()
        # Status bar is created BEFORE the notebook: SettingsTab calls
        # reload_config() during its construction, which refreshes this label.
        self.status = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status, style="Sub.TLabel",
                  font=FONT_MONO).pack(fill="x", side="bottom", padx=12, pady=(0, 6))
        if self.cfg_error:
            bar = ttk.Frame(self.root, style="Surface.TFrame", padding=(10, 6))
            bar.pack(fill="x", padx=10, pady=(6, 0))
            ttk.Label(bar, text=f"CONFIG ERROR - runs are blocked: {self.cfg_error}",
                      foreground=BM["error"], background=BM["surface"],
                      wraplength=1100, justify="left").pack(anchor="w")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        nb.add(CloudWatchTab(nb, self), text="CloudWatch estimate")
        nb.add(CostExplorerTab(nb, self), text="Cost Explorer (billed)")
        nb.add(CalibratedTab(nb, self), text="CE-calibrated")
        nb.add(DiscoveryTab(nb, self), text="Discovery")
        nb.add(SettingsTab(nb, self), text="Settings")

        self._refresh_status()

    # ------------------------------------------------------------------
    def _build_header(self):
        bar = ttk.Frame(self.root, style="Surface.TFrame", padding=(14, 10))
        bar.pack(fill="x")
        self._wordmark = None
        try:
            img = tk.PhotoImage(file=str(_asset("bm-wordmark.png")))
            if img.width() > 200:
                factor = max(1, round(img.width() / 200))
                img = img.subsample(factor, factor)
            self._wordmark = img
            tk.Label(bar, image=img, bg=BM["surface"], bd=0).pack(side="left",
                                                                  padx=(0, 14))
        except Exception:
            ttk.Label(bar, text="BUILDMANSHIPS",
                      style="SurfaceAccent.TLabel").pack(side="left", padx=(0, 14))
        ttk.Label(bar, text="Bedrock Cost Checker",
                  style="SurfaceTitle.TLabel").pack(side="left")
        ttk.Label(bar, text=f"v{__version__}  |  A Buildman Shipped Project",
                  style="SurfaceMuted.TLabel", font=FONT_SUB).pack(side="left",
                                                                   padx=(12, 0),
                                                                   pady=(6, 0))

    def _refresh_status(self):
        state, msg = creds_mod.status(self.cfg)
        self.status.set(f"config: {config_mod.config_path()}   |   credentials: {msg}")

    def credentials(self):
        return creds_mod.resolve(self.cfg)

    def reload_config(self):
        try:
            self.cfg = config_mod.load_config()
            self.cfg_error = None
        except config_mod.ConfigError as exc:
            self.cfg_error = str(exc)
        pricing.apply_overrides(self.cfg.get("pricing_overrides") or {})
        self._refresh_status()

    def run(self):
        self.root.mainloop()
        return 0


def main():
    return App().run()
