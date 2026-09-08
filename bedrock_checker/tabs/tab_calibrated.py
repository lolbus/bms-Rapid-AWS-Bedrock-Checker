"""Tab 3 - Method C: CE-calibrated estimate."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..methods import calibrated
from .base import RunnerTab


class CalibratedTab(RunnerTab):
    title = "Method C - CE-calibrated estimate"
    description = ("Fresh-window CloudWatch estimate corrected by factor = CE actual / estimate, "
                   "per class, over trailing FINALIZED days. Self-absorbs cache-TTL mix, Bedrock "
                   "premium and region coverage. A class with no finalized overlap keeps factor "
                   "1.000 and says so - factors are never shared across classes.")
    columns = ("day", "class", "estimate$", "CE billed$", "ratio")
    widths = (110, 90, 140, 140, 90)

    def build_controls(self, parent):
        cfg = self.app.cfg
        ttk.Label(parent, text="Hours back:").pack(side="left")
        self.hours = tk.StringVar(value=str(cfg["hours"]))
        ttk.Spinbox(parent, from_=1, to=8760, textvariable=self.hours,
                    width=8).pack(side="left", padx=(4, 12))
        ttk.Label(parent, text="Lookback days:").pack(side="left")
        self.lookback = tk.StringVar(value=str(cfg["calibration_lookback_days"]))
        ttk.Spinbox(parent, from_=3, to=60, textvariable=self.lookback,
                    width=6).pack(side="left", padx=(4, 12))
        ttk.Label(parent, text="Skip recent days:").pack(side="left")
        self.skip = tk.StringVar(value=str(cfg["calibration_skip_recent_days"]))
        ttk.Spinbox(parent, from_=0, to=7, textvariable=self.skip,
                    width=5).pack(side="left", padx=(4, 12))
        ttk.Label(parent, text="Regions (csv):").pack(side="left")
        self.regions = tk.StringVar(value=",".join(cfg["regions"]))
        ttk.Entry(parent, textvariable=self.regions,
                  width=24).pack(side="left", padx=(4, 0))

    def worker(self, kw):
        try:
            hours = float(self.hours.get())
            lookback = int(float(self.lookback.get()))
            skip = int(float(self.skip.get()))
        except ValueError:
            self.log_line("ERROR: hours / lookback / skip must be numbers.", "err")
            return
        regions = [r.strip() for r in self.regions.get().split(",") if r.strip()] or None
        classes = self.app.cfg["classes"]
        res = calibrated.run(hours, lookback, skip, regions, kw, dict(self.app.cfg),
                             classes, self.log_line, cancel=self._cancel)
        for row in res.get("table", []):
            ratio = "n/a" if row["ratio"] is None else f"{row['ratio']:.3f}"
            tags = ("warn",) if row["ratio"] is None else ()
            self.emit_row((row["day"], row["class"], f"{row['estimate']:,.4f}",
                           f"{row['ce']:,.4f}", ratio), tags)
        if res["status"] != "ok":
            self.log_line(f"ERROR: {res['status']}", "err")
            return
        totals = {}
        for c in classes:
            f = res["factors"][c]
            pc = res["per_class"][c]
            totals[c] = pc["calibrated"]
            if res["calibrated"][c]:
                self.log_line(f"  {c:<7} factor x{f:.3f}  raw ${pc['raw']:,.4f} -> "
                              f"calibrated ${pc['calibrated']:,.4f}", "accent")
            else:
                self.log_line(f"  {c:<7} factor x{f:.3f} (uncalibrated - no finalized "
                              f"overlap)  raw ${pc['raw']:,.4f}", "muted")
        raw_sum = sum(pc["raw"] for pc in res["per_class"].values())
        cal_sum = sum(totals.values())
        self.log_line(f"TOTAL raw ${raw_sum:,.4f} -> CALIBRATED ${cal_sum:,.4f}", "accent")
        self.log_line("Still an estimate for the unbilled window; CE (Method A) remains "
                      "truth once posted.", "muted")
        self.emit_rollup(totals)
