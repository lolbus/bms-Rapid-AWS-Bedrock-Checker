"""Tab 1 - Method B: CloudWatch list-price estimate."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..methods import cloudwatch
from .base import RunnerTab


class CloudWatchTab(RunnerTab):
    title = "Method B - CloudWatch estimate"
    description = ("AWS-recorded token counts from CloudWatch (AWS/Bedrock), priced with the "
                   "built-in rate card. Best for fresh windows (<48h) that Cost Explorer "
                   "has not finalized yet.")
    columns = ("region", "model_id", "class", "in", "out", "cache_r", "cache_w",
               "premium", "cost$")
    widths = (130, 300, 80, 90, 90, 90, 90, 80, 90)

    def build_controls(self, parent):
        cfg = self.app.cfg
        ttk.Label(parent, text="Hours back:").pack(side="left")
        self.hours = tk.StringVar(value=str(cfg["hours"]))
        ttk.Spinbox(parent, from_=1, to=8760, textvariable=self.hours,
                    width=8).pack(side="left", padx=(4, 12))

        ttk.Label(parent, text="Regions (csv):").pack(side="left")
        self.regions = tk.StringVar(value=",".join(cfg["regions"]))
        ttk.Entry(parent, textvariable=self.regions,
                  width=28).pack(side="left", padx=(4, 6))
        self.auto = tk.BooleanVar(value=cfg["auto_discover_regions"])
        ttk.Checkbutton(parent, text="auto-discover",
                        variable=self.auto).pack(side="left", padx=(0, 12))

        ttk.Label(parent, text="Cache write TTL:").pack(side="left")
        self.ttl = tk.StringVar(value=cfg["cache_write_ttl"])
        ttk.Radiobutton(parent, text="5m", variable=self.ttl, value="5m").pack(side="left")
        ttk.Radiobutton(parent, text="1h", variable=self.ttl,
                        value="1h").pack(side="left", padx=(0, 12))

        ttk.Label(parent, text="Regional premium %:").pack(side="left")
        self.premium = tk.StringVar(value=str(cfg["regional_premium_pct"]))
        ttk.Spinbox(parent, from_=0, to=50, textvariable=self.premium,
                    width=5).pack(side="left", padx=(4, 0))

    def worker(self, kw):
        try:
            hours = float(self.hours.get())
        except ValueError:
            self.log_line("ERROR: hours must be a number.", "err")
            return
        cfg = dict(self.app.cfg)
        cfg["cache_write_ttl"] = self.ttl.get()
        try:
            cfg["regional_premium_pct"] = float(self.premium.get())
        except ValueError:
            self.log_line("NOTE: premium not a number; using config value.", "warn")
        regions = None if self.auto.get() else [
            r.strip() for r in self.regions.get().split(",") if r.strip()] or None

        res = cloudwatch.scan(hours=hours, regions=regions, cw_kwargs=kw, cfg=cfg,
                              log=self.log_line, cancel=self._cancel)
        if res["status"] == "cancelled":
            return
        grand = 0.0
        totals = {}
        for r in sorted(res["rows"], key=lambda x: (x["class"], x["region"], x["model_id"])):
            c = r["costs"]
            grand += c["total"]
            totals[r["class"]] = totals.get(r["class"], 0.0) + c["total"]
            self.emit_row((r["region"], r["model_id"], r["class"],
                           f"{r['input']:,}", f"{r['output']:,}",
                           f"{r['cache_read']:,}", f"{r['cache_write']:,}",
                           f"{r['premium_pct']:g}%", f"{c['total']:,.4f}"))
        if not res["rows"]:
            self.log_line("No Claude Bedrock usage found in the window. "
                          "(Check regions, the hours window, or whether traffic ran.)",
                          "warn")
        self.log_line(f"GRAND TOTAL (USD), last {hours:g}h : ${grand:,.4f}", "accent")
        if hours:
            self.log_line(f"Burn rate: ${grand / hours:,.4f}/hour  ~= "
                          f"${grand / hours * 24:,.2f}/day", "muted")
        for e in res["errors"]:
            self.log_line(f"NOTE: skipped {e['region']}: {e['error']}", "warn")
        self.log_line("SOURCE: AWS/Bedrock CloudWatch token metrics x built-in rate card.",
                      "muted")
        self.emit_rollup(totals)
