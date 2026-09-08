"""Tab 4 - Method D: model & region discovery (read-only inventory)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..methods import discovery
from .base import RunnerTab


class DiscoveryTab(RunnerTab):
    title = "Method D - Model & region discovery"
    description = ("Read-only inventory of every AWS/Bedrock ModelId visible in CloudWatch per "
                   "region, its rate-card class, and its inference profile. UNMATCHED rows mean "
                   "the rate card needs a new row - that is how a new model release gets noticed.")
    columns = ("region", "model_id", "class", "label", "profile", "rates in/out")
    widths = (130, 320, 100, 220, 90, 120)

    def build_controls(self, parent):
        cfg = self.app.cfg
        ttk.Label(parent, text="Regions (csv):").pack(side="left")
        self.regions = tk.StringVar(value=",".join(cfg["regions"]))
        ttk.Entry(parent, textvariable=self.regions,
                  width=32).pack(side="left", padx=(4, 6))
        self.auto = tk.BooleanVar(value=cfg["auto_discover_regions"])
        ttk.Checkbutton(parent, text="auto-discover",
                        variable=self.auto).pack(side="left")

    def worker(self, kw):
        cfg = dict(self.app.cfg)
        cfg["auto_discover_regions"] = self.auto.get()
        cfg["regions"] = [r.strip() for r in self.regions.get().split(",") if r.strip()]
        res = discovery.run(kw, cfg, self.log_line, cancel=self._cancel)
        if res["status"] == "cancelled":
            return
        unmatched = 0
        for r in res["rows"]:
            tags = ("warn",) if r["class"] == "UNMATCHED" else ()
            if r["class"] == "UNMATCHED":
                unmatched += 1
            self.emit_row((r["region"], r["model_id"], r["class"], r["label"],
                           r["profile"], r["rates"]), tags)
        self.log_line(f"{len(res['rows'])} model id(s) discovered; {unmatched} UNMATCHED.",
                      "warn" if unmatched else "ok")
        for e in res["errors"]:
            self.log_line(f"NOTE: {e}", "warn")
        # Discovery has no cost: the rollup still prints, all zeros.
        self.emit_rollup({})
