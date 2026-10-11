"""Typeset equations for the quiz window.

Claude writes a quiz's equations in LaTeX (`$...$` inline, `$$...$$` on a line of its own). The window can't draw
those as text, so each one is drawn once into a small picture (matplotlib's own math typesetter, no TeX on the
computer) and placed in the text where it belongs. Anything the typesetter can't draw is shown as the LaTeX it
was written in, so a question is never lost. Pictures are kept in Oso's data folder, one per equation and size.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from . import config as cfgmod

log = logging.getLogger(__name__)

# $$...$$ first, so a display equation isn't read as two empty inline ones; an inline one has no blank edges and
# no newline, so a dollar amount ("$5 and $6") isn't taken for math.
_MATH = re.compile(r"\$\$(?P<display>.+?)\$\$|\$(?P<inline>(?=\S)[^$\n]+?(?<=\S))\$", re.S)
_FONT = "stix"


def split(text: str) -> list[tuple[str, str]]:
    """The text in order as ("text", ...), ("inline", latex), and ("display", latex) pieces."""
    out: list[tuple[str, str]] = []
    at = 0
    for m in _MATH.finditer(text):
        if m.start() > at:
            out.append(("text", text[at:m.start()]))
        if m.group("display") is not None:
            out.append(("display", m.group("display").strip()))
        else:
            out.append(("inline", m.group("inline")))
        at = m.end()
    if at < len(text):
        out.append(("text", text[at:]))
    return out


def has_math(text: str | None) -> bool:
    return bool(text) and _MATH.search(text) is not None


def folder() -> Path:
    p = cfgmod.data_dir() / "math"
    p.mkdir(parents=True, exist_ok=True)
    return p


def render(latex: str, size: float = 13.0, dpi: int = 110, display: bool = False) -> Path | None:
    """A PNG of one equation (or of a line of text with equations in it), or None when it can't be drawn."""
    key = hashlib.sha1(f"{_FONT}|{size}|{dpi}|{display}|{latex}".encode()).hexdigest()[:20]
    out = folder() / f"{key}.png"
    if out.exists():
        return out
    try:
        os.environ.setdefault("MPLCONFIGDIR", str(cfgmod.data_dir() / "matplotlib"))
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib.figure import Figure

        s = f"${latex}$" if display else latex
        fig = Figure(figsize=(0.1, 0.1))
        fig.text(0, 0, s, fontsize=size, math_fontfamily=_FONT, fontfamily="sans-serif")
        tmp = out.with_suffix(".part")
        fig.savefig(tmp, dpi=dpi, bbox_inches="tight", pad_inches=0.03, transparent=True, format="png")
        tmp.replace(out)
        return out
    except Exception as e:  # noqa: BLE001  a formula the typesetter can't draw stays as its LaTeX
        log.info("could not typeset %r: %s", latex[:60], type(e).__name__)
        return None


def fill(widget, text: str, size: float = 13.0, dpi: int = 110) -> None:
    """Put `text` into a tkinter Text widget with each equation drawn as a picture in its place."""
    import tkinter as tk

    photos = getattr(widget, "_oso_photos", None)
    if photos is None:
        photos = widget._oso_photos = []
    photos.clear()
    for kind, piece in split(text):
        if kind == "text":
            widget.insert("end", piece)
            continue
        latex = piece
        # Math is drawn a little larger than the text beside it, and a display equation larger still, since the
        # typesetter has no display style of its own (integral and sum signs grow with the size).
        image = render(f"${latex}$" if kind == "inline" else latex, size=size * (1.5 if kind == "display" else 1.1),
                       dpi=dpi, display=kind == "display")
        if image is None:
            widget.insert("end", f"${latex}$")
            continue
        try:
            photo = tk.PhotoImage(file=str(image), master=widget)
        except tk.TclError:
            widget.insert("end", f"${latex}$")
            continue
        photos.append(photo)
        if kind == "display":
            widget.insert("end", "\n")
            widget.image_create("end", image=photo, padx=12, pady=4)
            widget.insert("end", "\n")
        else:
            widget.image_create("end", image=photo, align="center", padx=2)


def picture(text: str, size: float = 13.0, dpi: int = 110):
    """One picture of a whole line (words and equations together) for a button or label, or None.
    Inline `$...$` is left for the typesetter; a display equation is drawn inline on the line."""
    line = text.replace("$$", "$")
    return render(line, size=size, dpi=dpi)


def dpi_of(widget) -> int:
    """Pixels per inch the window is drawn at, so pictures match its text size."""
    try:
        return max(72, int(round(72 * float(widget.tk.call("tk", "scaling")))))
    except Exception:  # noqa: BLE001
        return 110
