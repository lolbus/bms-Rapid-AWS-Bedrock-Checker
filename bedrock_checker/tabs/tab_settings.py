"""Tab 5 - Settings: config.json editor + credential status + rate card."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as config_mod
from .. import creds as creds_mod
from .. import pricing
from ..theme import BM, FONT_MONO

_FIELDS = [
    ("hours", "Default hours back (Method B/C)"),
    ("days", "Default days back (Method A)"),
    ("regions", "Regions (comma-separated)"),
    ("cache_write_ttl", "Cache write TTL (5m | 1h)"),
    ("regional_premium_pct", "Regional profile premium %"),
    ("calibration_lookback_days", "Calibration lookback days"),
    ("calibration_skip_recent_days", "Calibration skip recent days"),
    ("cloudwatch_period_s", "CloudWatch period (s)"),
    ("request_timeout_s", "AWS request timeout (s)"),
    ("max_worker_threads", "Max worker threads"),
    ("credentials_env_prefix", "Credential env prefix"),
]


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self._vars = {}

        ttk.Label(self, text="Settings", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="config.json beside the app. Tabs read these values as "
                             "startup defaults; the same parameters can be overridden "
                             "per run on each tab.",
                  style="Sub.TLabel", wraplength=1000, justify="left"
                  ).pack(anchor="w", pady=(2, 8))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        # -- left: config form -------------------------------------------
        form = ttk.Labelframe(body, text=" config.json ", padding=10)
        form.pack(side="left", fill="both", expand=True, padx=(0, 8))
        for key, label in _FIELDS:
            row = ttk.Frame(form)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=34).pack(side="left")
            var = tk.StringVar()
            self._vars[key] = var
            ttk.Entry(row, textvariable=var, width=34).pack(side="left")
        self.auto_var = tk.BooleanVar()
        ttk.Checkbutton(form, text="auto-discover regions (ec2:DescribeRegions)",
                        variable=self.auto_var).pack(anchor="w", pady=(6, 2))

        btns = ttk.Frame(form)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton",
                   command=self.on_save).pack(side="left")
        ttk.Button(btns, text="Reload from disk",
                   command=self.reload).pack(side="left", padx=8)
        ttk.Button(btns, text="Open folder",
                   command=self.open_folder).pack(side="left")

        self.path_label = ttk.Label(form, text="", style="Sub.TLabel",
                                    wraplength=520, justify="left")
        self.path_label.pack(anchor="w", pady=(8, 0))

        # -- right: credentials + rate card --------------------------------
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        cred = ttk.Labelframe(right, text=" credentials ", padding=10)
        cred.pack(fill="x", pady=(0, 8))
        ttk.Label(cred, text="Paste keys below, OR leave them empty and name the system "
                             "environment variables that hold them. Saved into config.json - "
                             "treat that file as a secret.",
                  style="Muted.TLabel", wraplength=460, justify="left").pack(anchor="w")

        self._cred_vars = {}
        self._cred_entries = []
        for key, label in (("access_key_id", "Access key ID (paste)"),
                           ("secret_access_key", "Secret access key (paste)"),
                           ("session_token", "Session token (paste, optional)")):
            row = ttk.Frame(cred)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=30).pack(side="left")
            var = tk.StringVar()
            self._cred_vars[key] = var
            ent = ttk.Entry(row, textvariable=var, width=34, show="\u2022")
            ent.pack(side="left")
            self._cred_entries.append(ent)
        self._show_creds = tk.BooleanVar(value=False)
        ttk.Checkbutton(cred, text="show pasted keys", variable=self._show_creds,
                        command=self._toggle_show).pack(anchor="w", pady=(2, 6))

        self._env_vars = {}
        for key, label in (("access_key_id_env", "...or env var for key ID"),
                           ("secret_access_key_env", "...or env var for secret"),
                           ("session_token_env", "...or env var for token")):
            row = ttk.Frame(cred)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=30).pack(side="left")
            var = tk.StringVar()
            self._env_vars[key] = var
            ttk.Entry(row, textvariable=var, width=34).pack(side="left")

        self.cred_status = ttk.Label(cred, text="", font=FONT_MONO,
                                     wraplength=460, justify="left")
        self.cred_status.pack(anchor="w", pady=(6, 0))
        ttk.Button(cred, text="Re-check", command=self._refresh_creds
                   ).pack(anchor="w", pady=(8, 0))

        card = ttk.Labelframe(right, text=" rate card (USD per 1M tokens) ", padding=6)
        card.pack(fill="both", expand=True)
        from ..widgets import make_tree
        tree_frame, self.rate_tree = make_tree(
            card, ("pattern", "class", "in", "out", "cache_r", "cw_5m", "cw_1h"),
            widths=(140, 70, 60, 60, 70, 70, 70), height=9)
        tree_frame.pack(fill="both", expand=True)
        for i, (pat, cls, _label, ci, co, cr, c5, c1h) in enumerate(pricing.RATE_CARD):
            self.rate_tree.insert("", "end",
                                  values=(pat, cls, f"{ci:g}", f"{co:g}", f"{cr:g}",
                                          f"{c5:g}", f"{c1h:g}"),
                                  tags=(("odd",) if i % 2 else ()))
        ttk.Label(card, text="First substring match wins; legacy rows precede generic "
                             "ones. Override per class via pricing_overrides in config.json.",
                  style="Muted.TLabel", wraplength=460, justify="left"
                  ).pack(anchor="w", pady=(6, 2))

        self.reload()
        self._refresh_creds()

    # ------------------------------------------------------------------
    def _toggle_show(self):
        show = "" if self._show_creds.get() else "\u2022"
        for ent in self._cred_entries:
            ent.configure(show=show)

    def reload(self):
        self.app.reload_config()
        cfg = self.app.cfg
        for key, _ in _FIELDS:
            v = cfg.get(key, "")
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            self._vars[key].set(str(v))
        self.auto_var.set(bool(cfg.get("auto_discover_regions")))
        block = cfg.get("credentials") or {}
        for key, var in self._cred_vars.items():
            var.set(str(block.get(key) or ""))
        for key, var in self._env_vars.items():
            var.set(str(block.get(key) or ""))
        self.path_label.configure(text=f"file: {config_mod.config_path()}")
        if self.app.cfg_error:
            messagebox.showerror("Config error", self.app.cfg_error, parent=self)

    def on_save(self):
        cfg = dict(self.app.cfg)
        try:
            cfg["hours"] = float(self._vars["hours"].get())
            cfg["days"] = int(float(self._vars["days"].get()))
            cfg["regions"] = [r.strip() for r in self._vars["regions"].get().split(",")
                              if r.strip()]
            ttl = self._vars["cache_write_ttl"].get().strip()
            if ttl not in ("5m", "1h"):
                raise ValueError("cache_write_ttl must be '5m' or '1h'")
            cfg["cache_write_ttl"] = ttl
            cfg["regional_premium_pct"] = float(self._vars["regional_premium_pct"].get())
            cfg["calibration_lookback_days"] = int(float(
                self._vars["calibration_lookback_days"].get()))
            cfg["calibration_skip_recent_days"] = int(float(
                self._vars["calibration_skip_recent_days"].get()))
            cfg["cloudwatch_period_s"] = int(float(self._vars["cloudwatch_period_s"].get()))
            cfg["request_timeout_s"] = int(float(self._vars["request_timeout_s"].get()))
            cfg["max_worker_threads"] = int(float(self._vars["max_worker_threads"].get()))
            cfg["credentials_env_prefix"] = (
                self._vars["credentials_env_prefix"].get().strip() or "EVAL_AWS")
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return
        cfg["auto_discover_regions"] = bool(self.auto_var.get())
        cfg["credentials"] = {
            **{k: v.get().strip() for k, v in self._cred_vars.items()},
            **{k: v.get().strip() for k, v in self._env_vars.items()},
        }
        try:
            path = config_mod.save_config(cfg)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        self.app.cfg = cfg
        self.app.cfg_error = None
        self.path_label.configure(text=f"saved: {path}")
        self._refresh_creds()

    def open_folder(self):
        folder = str(config_mod.app_dir())
        try:
            os.startfile(folder)  # Windows-only, which is all this build targets
        except OSError as exc:
            messagebox.showerror("Open folder failed", str(exc), parent=self)

    def _refresh_creds(self):
        state, msg = creds_mod.status(self.app.cfg)
        prefix = "OK  " if state == "ok" else "MISSING  "
        self.cred_status.configure(
            text=prefix + msg,
            foreground=BM["success"] if state == "ok" else BM["error"])
        self.app._refresh_status()
