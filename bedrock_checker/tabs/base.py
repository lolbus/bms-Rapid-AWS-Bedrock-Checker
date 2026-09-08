"""RunnerTab: control strip + run/cancel + tree + log + rollup, threaded.

boto3 never runs on the Tk main thread. The worker thread emits through a
queue; the main thread drains it every 100 ms. Cancel is a threading.Event
checked between regions by the methods.
"""
from __future__ import annotations

import queue
import threading
from tkinter import ttk

from .. import widgets


class RunnerTab(ttk.Frame):
    title = "Tab"
    description = ""
    columns = ()
    widths = None

    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self._queue = queue.Queue()
        self._cancel = threading.Event()
        self._worker = None

        ttk.Label(self, text=self.title, style="Title.TLabel").pack(anchor="w")
        if self.description:
            ttk.Label(self, text=self.description, style="Sub.TLabel",
                      wraplength=1000, justify="left").pack(anchor="w", pady=(2, 8))

        self.controls = ttk.Frame(self)
        self.controls.pack(fill="x", pady=(0, 8))
        self.build_controls(self.controls)
        self.cancel_btn = ttk.Button(self.controls, text="Cancel",
                                     command=self._cancel.set, state="disabled")
        self.run_btn = ttk.Button(self.controls, text="Run", style="Accent.TButton",
                                  command=self.on_run)
        self.cancel_btn.pack(side="right")
        self.run_btn.pack(side="right", padx=(0, 6))

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True)
        tree_frame, self.tree = widgets.make_tree(mid, self.columns, self.widths)
        tree_frame.pack(fill="both", expand=True)

        bottom = ttk.Frame(self)
        bottom.pack(fill="both", pady=(8, 0))
        left = ttk.Frame(bottom)
        left.pack(side="left", fill="both", expand=True)
        log_frame = ttk.Frame(left)
        log_frame.pack(fill="both", expand=True)
        self.log = widgets.make_log_pane(log_frame, height=9)
        self.rollup = widgets.RollupBlock(bottom, self.app.cfg["classes"])
        self.rollup.pack(side="right", fill="y", padx=(10, 0))

        self.after(100, self._drain)

    # -- subclass hooks ---------------------------------------------------
    def build_controls(self, parent):
        """Add parameter widgets (pack side='left'). Subclass implements."""
        raise NotImplementedError

    def worker(self, kw):
        """Blocking AWS work off the UI thread. Subclass implements."""
        raise NotImplementedError

    # -- run lifecycle ----------------------------------------------------
    def on_run(self):
        if self.app.cfg_error:
            self.log_line(f"ERROR: config: {self.app.cfg_error}", "err")
            return
        kw, msg = self.app.credentials()
        if kw is None:
            self.log_line(f"ERROR: {msg}", "err")
            return
        self.log_line(f"credentials: {msg}", "muted")
        self._cancel.clear()
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.tree.delete(*self.tree.get_children())
        self._worker = threading.Thread(target=self._run_safe, args=(kw,),
                                        daemon=True)
        self._worker.start()

    def _run_safe(self, kw):
        try:
            self.worker(kw)
        except Exception as exc:  # surfaced to the UI, never swallowed
            self._queue.put(("log", (f"ERROR: {type(exc).__name__}: {exc}", "err")))
        finally:
            self._queue.put(("finished", None))

    def _drain(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    msg, tag = payload
                    widgets.log_write(self.log, msg, tag)
                elif kind == "row":
                    values, tags = payload
                    n = len(self.tree.get_children())
                    parity = ("odd",) if n % 2 else ()
                    self.tree.insert("", "end", values=values,
                                     tags=tuple(tags) + parity)
                elif kind == "rollup":
                    self.rollup.update_totals(payload)
                elif kind == "finished":
                    self.run_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    # -- worker-side emitters (thread-safe via the queue) ------------------
    def log_line(self, msg, tag=None):
        self._queue.put(("log", (msg, tag)))

    def emit_row(self, values, tags=()):
        self._queue.put(("row", (values, tags)))

    def emit_rollup(self, totals):
        self._queue.put(("rollup", totals))
