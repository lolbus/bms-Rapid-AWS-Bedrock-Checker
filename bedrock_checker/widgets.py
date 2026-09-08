"""Shared widgets: the class rollup block, log pane, tree builder."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import BM, FONT_MONO, style_log_text


def render_rollup(totals: dict, classes: list) -> str:
    """The required class rollup. Every class printed, zeros included:

        Usage analysis result:
        USD$0.00 sonnet
        USD$103.84 opus
        USD$0.80 fable
    """
    lines = ["Usage analysis result:"]
    for cls in classes:
        lines.append(f"USD${totals.get(cls, 0.0):,.2f} {cls}")
    return "\n".join(lines)


class RollupBlock(ttk.Frame):
    """Mono, one line per class. Zero is printed, never skipped."""

    def __init__(self, parent, classes):
        super().__init__(parent, style="Surface.TFrame", padding=12)
        self.classes = list(classes)
        ttk.Label(self, text="Usage analysis result:", style="SurfaceMuted.TLabel",
                  font=FONT_MONO).pack(anchor="w")
        ttk.Label(self, text="(no run yet - all zeros)", style="SurfaceMuted.TLabel",
                  font=FONT_MONO).pack(anchor="w", pady=(0, 4))
        self._vars = {}
        self._labels = {}
        self._totals = {c: 0.0 for c in self.classes}
        for cls in self.classes:
            var = tk.StringVar(value=f"USD$0.00 {cls}")
            self._vars[cls] = var
            lbl = ttk.Label(self, textvariable=var, style="SurfaceMono.TLabel")
            lbl.pack(anchor="w")
            self._labels[cls] = lbl

    def update_totals(self, totals: dict):
        self._totals = {c: float(totals.get(c, 0.0)) for c in self.classes}
        for cls, var in self._vars.items():
            var.set(f"USD${self._totals[cls]:,.2f} {cls}")

    def totals(self):
        return dict(self._totals)


def make_log_pane(parent, height=10) -> tk.Text:
    text = tk.Text(parent, height=height)
    style_log_text(text)
    sb = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    return text


def log_write(widget: tk.Text, msg: str, tag: str | None = None):
    widget.configure(state="normal")
    widget.insert("end", msg + "\n", (tag,) if tag else ())
    widget.see("end")
    widget.configure(state="disabled")


def make_tree(parent, columns, widths=None, height=8):
    """Dark Treeview with scrollbars. Tags: 'odd' (stripe), 'warn', 'err', 'ok'.
    Put semantic tags BEFORE 'odd' in an item's tag list so they win conflicts."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
    for i, col in enumerate(columns):
        tree.heading(col, text=col)
        tree.column(col, width=(widths[i] if widths else 110), anchor="w", stretch=True)
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tree.tag_configure("odd", background=BM["surface2"])
    tree.tag_configure("warn", foreground=BM["warning"])
    tree.tag_configure("err", foreground=BM["error"])
    tree.tag_configure("ok", foreground=BM["success"])
    return frame, tree
