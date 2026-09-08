"""BUILDMANSHIPS personal-brand theme for ttk.

Deep violet-black canvas, one neon-violet accent, mono for anything a machine
produced. Tokens come from the personal-brand-theme-ui skill - do not
hand-pick hexes. Rules that matter here:
- theme_use("clam") FIRST: vista/xpnative ignore background colours.
- One accent (#C361FA): active tab + primary Run button only. No glow except
  the header wordmark.
- Mono carries machine output (model IDs, tokens, dollars, timestamps); sans
  carries prose.
- #7E56B7 (dim) is borders/decoration only, never text.
- Status is never colour-only: always a text label too.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BM = {
    "void": "#08010F", "bg": "#0D0224", "surface": "#160636",
    "surface2": "#1E0A4A", "line": "#2F1568", "line_soft": "#210E4D",
    "violet900": "#3B0F8F", "violet700": "#4B0AB7", "violet600": "#6C22DA",
    "violet500": "#8B45F0", "violet400": "#A855F7", "violet300": "#C361FA",
    "violet200": "#DABFF4",
    "text": "#EDE7FB", "text2": "#C9B6EE", "muted": "#A98FD4", "dim": "#7E56B7",
    "success": "#34D399", "warning": "#FBBF24", "error": "#FB7185",
    "info": "#38BDF8",
}

FONT_SANS = ("Segoe UI", 10)
FONT_SANS_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SUB = ("Segoe UI", 9)
FONT_MONO = ("Cascadia Mono", 10)
FONT_MONO_BOLD = ("Cascadia Mono", 10, "bold")


def apply(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=BM["bg"])
    style.configure(".", background=BM["bg"], foreground=BM["text"],
                    fieldbackground=BM["surface"], font=FONT_SANS,
                    bordercolor=BM["line"], troughcolor=BM["surface"],
                    focuscolor=BM["violet500"], arrowcolor=BM["muted"])

    style.configure("TFrame", background=BM["bg"])
    style.configure("Surface.TFrame", background=BM["surface"])

    style.configure("TLabel", background=BM["bg"], foreground=BM["text"])
    style.configure("Muted.TLabel", foreground=BM["muted"])
    style.configure("Accent.TLabel", foreground=BM["violet300"], font=FONT_MONO_BOLD)
    style.configure("Title.TLabel", font=FONT_TITLE, foreground=BM["text"])
    style.configure("Sub.TLabel", font=FONT_SUB, foreground=BM["muted"])
    style.configure("Surface.TLabel", background=BM["surface"], foreground=BM["text"])
    style.configure("SurfaceTitle.TLabel", background=BM["surface"],
                    foreground=BM["text"], font=FONT_TITLE)
    style.configure("SurfaceMuted.TLabel", background=BM["surface"], foreground=BM["muted"])
    style.configure("SurfaceMono.TLabel", background=BM["surface"],
                    foreground=BM["text2"], font=FONT_MONO)
    style.configure("SurfaceAccent.TLabel", background=BM["surface"],
                    foreground=BM["violet300"], font=FONT_MONO_BOLD)

    style.configure("TButton", background=BM["surface2"], foreground=BM["text"],
                    bordercolor=BM["line"], padding=(12, 6))
    style.map("TButton",
              background=[("active", BM["violet700"]), ("disabled", BM["surface"])],
              foreground=[("disabled", BM["dim"])])

    # THE one accent: the primary action button.
    style.configure("Accent.TButton", background=BM["violet600"], foreground="#FFFFFF",
                    bordercolor=BM["violet500"], padding=(14, 7), font=FONT_SANS_BOLD)
    style.map("Accent.TButton",
              background=[("active", BM["violet500"]), ("disabled", BM["surface"])],
              foreground=[("disabled", BM["dim"])])

    style.configure("TNotebook", background=BM["bg"], bordercolor=BM["line"])
    style.configure("TNotebook.Tab", background=BM["surface"], foreground=BM["muted"],
                    padding=(14, 8))
    style.map("TNotebook.Tab",
              background=[("selected", BM["surface2"])],
              foreground=[("selected", BM["violet300"])])

    style.configure("Treeview", background=BM["surface"], fieldbackground=BM["surface"],
                    foreground=BM["text2"], bordercolor=BM["line"], borderwidth=1,
                    rowheight=24, font=FONT_MONO)
    style.configure("Treeview.Heading", background=BM["surface2"], foreground=BM["muted"],
                    bordercolor=BM["line"], font=FONT_SANS_BOLD)
    style.map("Treeview",
              background=[("selected", BM["violet900"])],
              foreground=[("selected", BM["text"])])

    for w in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(w, fieldbackground=BM["surface"], foreground=BM["text"],
                        bordercolor=BM["line"], insertcolor=BM["text"],
                        arrowcolor=BM["muted"])
    style.map("TCombobox", fieldbackground=[("readonly", BM["surface"])],
              foreground=[("readonly", BM["text"])])

    style.configure("TCheckbutton", background=BM["bg"], foreground=BM["text2"])
    style.configure("TRadiobutton", background=BM["bg"], foreground=BM["text2"])
    style.map("TCheckbutton", background=[("active", BM["bg"])],
              foreground=[("disabled", BM["dim"])])
    style.map("TRadiobutton", background=[("active", BM["bg"])])

    style.configure("TLabelframe", background=BM["bg"], foreground=BM["muted"],
                    bordercolor=BM["line"])
    style.configure("TLabelframe.Label", background=BM["bg"], foreground=BM["muted"])
    style.configure("TSeparator", background=BM["line"])
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=BM["surface2"],
                        troughcolor=BM["surface"], bordercolor=BM["line"],
                        arrowcolor=BM["muted"])
    return style


def style_log_text(widget: tk.Text) -> tk.Text:
    """Mono dark log pane with semantic tags. Colour is never the only signal -
    callers prefix lines with text like ERROR:/NOTE: as well as tagging."""
    widget.configure(
        bg=BM["void"], fg=BM["text2"], insertbackground=BM["text"],
        selectbackground=BM["violet900"], selectforeground=BM["text"],
        font=FONT_MONO, relief="flat", borderwidth=0, highlightthickness=1,
        highlightbackground=BM["line"], highlightcolor=BM["violet500"],
        wrap="none", state="disabled",
    )
    widget.tag_configure("ok", foreground=BM["success"])
    widget.tag_configure("warn", foreground=BM["warning"])
    widget.tag_configure("err", foreground=BM["error"])
    widget.tag_configure("info", foreground=BM["info"])
    widget.tag_configure("accent", foreground=BM["violet300"])
    widget.tag_configure("muted", foreground=BM["muted"])
    return widget
