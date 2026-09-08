"""Tab 2 - Method A: Cost Explorer (actual billed USD)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..methods import cost_explorer
from .base import RunnerTab


class CostExplorerTab(RunnerTab):
    title = "Method A - Cost Explorer (billed)"
    description = ("ACTUAL billed USD (UnblendedCost) per model per day - the source of truth. "
                   "Daily granularity, lags 1-2 days: today/yesterday read $0 'est' until AWS "
                   "finalizes, so use Method B for a fresh window.")
    columns = ("day", "service", "class", "billed$", "flag")
    widths = (110, 430, 90, 110, 70)

    def build_controls(self, parent):
        cfg = self.app.cfg
        ttk.Label(parent, text="Days back:").pack(side="left")
        self.days = tk.StringVar(value=str(cfg["days"]))
        ttk.Spinbox(parent, from_=1, to=90, textvariable=self.days,
                    width=6).pack(side="left", padx=(4, 12))
        ttk.Label(parent, text="Granularity:").pack(side="left")
        self.gran = tk.StringVar(value="DAILY")
        ttk.Combobox(parent, textvariable=self.gran, values=("DAILY", "MONTHLY"),
                     width=9, state="readonly").pack(side="left", padx=(4, 0))

    def worker(self, kw):
        try:
            days = int(float(self.days.get()))
        except ValueError:
            self.log_line("ERROR: days must be a number.", "err")
            return
        res = cost_explorer.report(days, self.gran.get(), kw, self.log_line)
        if res["status"] != "ok":
            self.log_line(f"ERROR: {res['status']}", "err")
            self.log_line("The IAM principal likely lacks ce:GetCostAndUsage.", "muted")
            return
        totals, other, grand = {}, 0.0, 0.0
        for r in res["rows"]:
            grand += r["amount"]
            tags = ("warn",) if r["flag"] == "est" else ()
            if r["class"] == "other":
                other += r["amount"]
            else:
                totals[r["class"]] = totals.get(r["class"], 0.0) + r["amount"]
            self.emit_row((r["day"], r["service"], r["class"],
                           f"{r['amount']:,.4f}", r["flag"]), tags)
        if not res["rows"]:
            self.log_line("(no Claude-on-Bedrock billed line items yet - recent days "
                          "may not have posted)", "warn")
        self.log_line(f"GRAND TOTAL billed (USD), last {days}d : ${grand:,.4f}", "accent")
        if other:
            self.log_line(f"  incl. ${other:,.4f} non-Claude Bedrock marketplace "
                          "(shown as 'other', not in rollup)", "muted")
        self.log_line("NOTE: today/yesterday usually read $0 'est' until AWS finalizes.",
                      "muted")
        self.emit_rollup(totals)
