"""Typeset equations for the quiz window.

Claude writes a quiz's equations in LaTeX (`$...$` inline, `$$...$$` on a line of its own). The window can't draw
those as text, so each one is drawn once into a small picture (matplotlib's own math typesetter, no TeX on the
computer) and placed in the text where it belongs. The typesetter draws one line at a time, so matrices,
multi-line derivations (`aligned`, `align`, `gather`, `\\`), and piecewise definitions (`cases`) are laid out
here: each cell or line is drawn on its own and the pieces are arranged on a grid, with the brackets drawn
around it. Anything that still can't be drawn is shown as the LaTeX it was written in, so a question is never
lost. Pictures are kept in Oso's data folder, one per equation and size.
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
        tmp = out.with_suffix(".part")
        _draw(tmp, latex, size, dpi, display)
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


def fit(widget, at_least: int = 1, at_most: int = 14) -> None:
    """Give a Text widget as many rows as its contents take, so a tall picture (a matrix, a derivation) isn't cut off."""
    import tkinter.font as tkfont

    try:
        widget.update_idletasks()
        px = widget.count("1.0", "end", "ypixels")
        if isinstance(px, (tuple, list)):
            px = px[0]
        line = tkfont.Font(root=widget, font=widget.cget("font")).metrics("linespace")
        rows = -(-int(px) // max(1, int(line)))
        widget.config(height=max(at_least, min(at_most, rows)))
    except Exception:  # noqa: BLE001  the window still works at its default height
        pass


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


# ---- laying out matrices and multi-line math ------------------------------------------------------------------
#
# Everything below works in pixels. A box knows its width and how far it reaches above (asc) and below (desc) the
# baseline of the text around it. Plain runs of text and math are measured by matplotlib; grids are built from
# their cells. Drawing places each piece on one figure and saves it.

_MATRIX = {"matrix": ("", ""), "pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("{", "}"),
           "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"), "smallmatrix": ("", "")}
_ALIGNED = {"aligned", "align", "align*", "alignat", "alignat*", "split", "eqnarray", "eqnarray*", "flalign", "flalign*"}
_GATHER = {"gather", "gather*", "gathered", "multline", "multline*"}
_BEGIN = re.compile(r"\\begin\{([a-zA-Z]+\*?)\}")
_END = re.compile(r"\\end\{([a-zA-Z]+\*?)\}")
_LEFT = re.compile(r"\\left\s*(\\\{|\\\}|\\\||\\lbrack|\\rbrack|\\lbrace|\\rbrace|\\vert|\\Vert|[(\[|.])\s*$")
_RIGHT = re.compile(r"^\s*\\right\s*(\\\{|\\\}|\\\||\\lbrack|\\rbrack|\\lbrace|\\rbrace|\\vert|\\Vert|[)\]|.])")
_DELIM_WORDS = {"\\{": "{", "\\}": "}", "\\|": "‖", "\\lbrack": "[", "\\rbrack": "]", "\\lbrace": "{", "\\rbrace": "}",
                "\\vert": "|", "\\Vert": "‖", ".": ""}

def _spaced(words: str) -> str:
    """Words for \\mathrm: each bare space made a visible one (a space already escaped is left alone)."""
    return re.sub(r"(?<!\\) ", "\\ ", words)


_SWAPS = [
    (re.compile(r"\s*\n\s*"), " "),  # a line break inside an equation is only spacing
    (re.compile(r"\\\\\[[^\]]*\]"), r"\\\\"),  # \\[4pt] is just a line break here
    (re.compile(r"\\(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle|limits|nolimits|notag|nonumber|hline)\b"), ""),
    (re.compile(r"\\(?:label|tag)\{[^{}]*\}"), ""),
    (re.compile(r"\\[dt]frac\b"), r"\\frac"),
    (re.compile(r"\\boldsymbol\b"), r"\\mathbf"),
    (re.compile(r"\\(?:operatorname|mbox|textrm|mathrm)\*?\{([^{}]*)\}"), lambda m: "\\mathrm{" + _spaced(m.group(1)) + "}"),
    (re.compile(r"\\text\{([^{}]*)\}"), lambda m: "\\mathrm{" + _spaced(m.group(1)) + "}"),
    (re.compile(r"\\textbf\{([^{}]*)\}"), lambda m: "\\mathbf{" + _spaced(m.group(1)) + "}"),
    (re.compile(r"\\textit\{([^{}]*)\}"), lambda m: "\\mathit{" + _spaced(m.group(1)) + "}"),
    (re.compile(r"\\implies\b"), r"\\Rightarrow"),
    (re.compile(r"\\iff\b"), r"\\Leftrightarrow"),
    (re.compile(r"\\degree\b"), r"^\\circ"),
    (re.compile(r"\\ge\b"), r"\\geq"),
    (re.compile(r"\\le\b"), r"\\leq"),
    (re.compile(r"\\ne\b"), r"\\neq"),
    (re.compile(r"\\dots\b"), r"\\ldots"),
    (re.compile(r"\\bm\b"), r"\\mathbf"),
]


def _clean(latex: str) -> str:
    """LaTeX the typesetter accepts: the commands it lacks are swapped for ones it has, or dropped when they only
    affect spacing or numbering."""
    for pat, rep in _SWAPS:
        latex = pat.sub(rep, latex)
    return latex


def _cut(s: str, sep: str) -> list[str]:
    """Split on `\\\\` or `&` at the top level: not inside braces, and not inside a `\\begin...\\end` block."""
    parts: list[str] = []
    buf: list[str] = []
    depth = brace = 0
    i = 0
    while i < len(s):
        if s.startswith("\\begin{", i) or s.startswith("\\end{", i):
            j = s.index("}", i) + 1
            depth += 1 if s[i + 1] == "b" else -1
            buf.append(s[i:j])
            i = j
            continue
        if s[i] == "\\" and i + 1 < len(s):
            two = s[i:i + 2]
            if two == sep and depth == 0 and brace == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(two)
            i += 2
            continue
        if s[i] == "{":
            brace += 1
        elif s[i] == "}":
            brace -= 1
        if s[i] == sep and depth == 0 and brace == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(s[i])
        i += 1
    parts.append("".join(buf))
    return parts


def _find_env(s: str) -> tuple[int, int, str, str] | None:
    """The first top-level environment in `s`: (start, end, name, body), or None."""
    m = _BEGIN.search(s)
    if m is None:
        return None
    depth = 1
    at = m.end()
    while depth:
        b, e = _BEGIN.search(s, at), _END.search(s, at)
        if e is None:
            raise ValueError(f"\\begin{{{m.group(1)}}} without its \\end")
        if b is not None and b.start() < e.start():
            depth += 1
            at = b.end()
        else:
            depth -= 1
            at = e.end()
            last = e
    return m.start(), last.end(), m.group(1), s[m.end():last.start()]


def _needs_layout(latex: str) -> bool:
    return "\\begin{" in latex or "\\\\" in latex or "&" in latex


class _Sheet:
    """One figure being drawn, with the measurements the boxes need."""

    def __init__(self, size: float, dpi: int):
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        self.fig = Figure(figsize=(1, 1), dpi=dpi)
        self.renderer = FigureCanvasAgg(self.fig).get_renderer()
        self.size, self.dpi = size, dpi
        self.em = size * dpi / 72
        eq = _Text(self, "$=$")  # the height of the "math axis": where a matrix or a fraction bar is centered
        self.axis = (eq.asc - eq.desc) / 2
        eq.t.remove()
        self.stroke = 0.055 * self.em * 72 / dpi  # the brackets' line width, in points

    def text(self, s: str, x: float, y: float):
        return self.fig.text(x / self.dpi, y / self.dpi, s, fontsize=self.size, math_fontfamily=_FONT, fontfamily="sans-serif",
                             va="baseline", ha="left", transform=self.fig.dpi_scale_trans)

    def line(self, points: list[tuple[float, float]]) -> None:
        from matplotlib.lines import Line2D

        self.fig.add_artist(Line2D([p[0] / self.dpi for p in points], [p[1] / self.dpi for p in points], transform=self.fig.dpi_scale_trans,
                                   color="black", linewidth=self.stroke, solid_capstyle="round", solid_joinstyle="round"))

    def curve(self, p0, c0, c1, p1) -> None:
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MPath

        pts = [(p[0] / self.dpi, p[1] / self.dpi) for p in (p0, c0, c1, p1)]
        path = MPath(pts, [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4])
        self.fig.add_artist(PathPatch(path, transform=self.fig.dpi_scale_trans, fill=False, edgecolor="black",
                                      linewidth=self.stroke, capstyle="round"))


class _Box:
    w = 0.0
    asc = 0.0
    desc = 0.0

    def draw(self, x: float, y: float) -> None:  # x: left edge, y: baseline (pixels from the bottom)
        pass


class _Text(_Box):
    """A run of text and inline math, measured by the typesetter."""

    def __init__(self, sheet: _Sheet, s: str):
        self.t = sheet.text(s, 0, 0)
        bb = self.t.get_window_extent(sheet.renderer)
        self.x0 = bb.x0
        self.w = bb.width
        self.asc, self.desc = max(bb.y1, 0.0), max(-bb.y0, 0.0)
        self.sheet = sheet

    def draw(self, x: float, y: float) -> None:
        self.t.set_position(((x - self.x0) / self.sheet.dpi, y / self.sheet.dpi))


class _Row(_Box):
    """Boxes side by side on one baseline."""

    def __init__(self, parts: list[_Box], gap: float = 0.0):
        self.parts, self.gap = parts, gap
        self.w = sum(p.w for p in parts) + gap * max(0, len(parts) - 1)
        self.asc = max((p.asc for p in parts), default=0.0)
        self.desc = max((p.desc for p in parts), default=0.0)

    def draw(self, x: float, y: float) -> None:
        for p in self.parts:
            p.draw(x, y)
            x += p.w + self.gap


class _Grid(_Box):
    """Cells on a grid, centered on the math axis, with brackets drawn around it when asked."""

    def __init__(self, sheet: _Sheet, rows: list[list[_Box]], aligns: list[str], gaps: list[float], rowgap: float,
                 delims: tuple[str, str]):
        self.sheet, self.rows, self.delims = sheet, rows, delims
        em = sheet.em
        ncols = max(len(r) for r in rows)
        self.aligns = [aligns[min(j, len(aligns) - 1)] for j in range(ncols)]
        self.gaps = [gaps[min(j, len(gaps) - 1)] for j in range(ncols)]
        self.widths = [max((r[j].w for r in rows if j < len(r)), default=0.0) for j in range(ncols)]
        self.heights = [(max(max((c.asc for c in r), default=0.0), 0.7 * em), max(max((c.desc for c in r), default=0.0), 0.2 * em)) for r in rows]
        self.rowgap = rowgap
        inner_w = sum(self.widths) + sum(self.gaps[:ncols - 1])
        inner_h = sum(a + d for a, d in self.heights) + rowgap * (len(rows) - 1)
        self.pad = 0.15 * em
        self.dw = [0.5 * em if d else 0.0 for d in delims]
        self.w = inner_w + self.dw[0] + self.dw[1]
        h = inner_h + 2 * self.pad
        self.asc, self.desc = sheet.axis + h / 2, h / 2 - sheet.axis

    def draw(self, x: float, y: float) -> None:
        top = y + self.asc - self.pad
        left = x + self.dw[0]
        for r, (ra, rd) in zip(self.rows, self.heights):
            base = top - ra
            cx = left
            for j, cell in enumerate(r):
                off = {"l": 0.0, "c": (self.widths[j] - cell.w) / 2, "r": self.widths[j] - cell.w}[self.aligns[j]]
                cell.draw(cx + off, base)
                cx += self.widths[j] + self.gaps[j]
            top = base - rd - self.rowgap
        lo, hi = y - self.desc, y + self.asc
        if self.delims[0]:
            self._delim(self.delims[0], x, lo, hi, 1)
        if self.delims[1]:
            self._delim(self.delims[1], x + self.w - self.dw[1], lo, hi, -1)

    def _delim(self, kind: str, x: float, lo: float, hi: float, side: int) -> None:
        """One bracket between lo and hi; side 1 opens to the right, -1 to the left."""
        s, em = self.sheet, self.sheet.em
        w = 0.28 * em
        spine = x + 0.1 * em if side == 1 else x + self.dw[1] - 0.1 * em
        tip = spine + side * w
        mid = (lo + hi) / 2
        if kind in ("(", ")"):
            bulge = spine - side * 0.55 * w
            s.curve((tip, hi), (bulge, hi - 0.15 * (hi - lo)), (bulge, lo + 0.15 * (hi - lo)), (tip, lo))
        elif kind in ("[", "]"):
            s.line([(tip, hi), (spine, hi), (spine, lo), (tip, lo)])
        elif kind in ("{", "}"):
            nub = spine - side * 0.4 * w
            knee = spine + side * 0.15 * w
            s.line([(tip, hi), (knee, hi - 0.12 * em), (knee, mid + 0.12 * em), (nub, mid), (knee, mid - 0.12 * em), (knee, lo + 0.12 * em), (tip, lo)])
        elif kind == "‖":
            s.line([(spine, hi), (spine, lo)])
            s.line([(spine + side * 0.18 * em, hi), (spine + side * 0.18 * em, lo)])
        else:  # "|"
            s.line([(spine + side * 0.1 * em, hi), (spine + side * 0.1 * em, lo)])


def _math_box(sheet: _Sheet, latex: str) -> _Box:
    """A box for the inside of one `$...$`: plain math, or rows and columns when it has line breaks or `&`."""
    latex = _clean(latex)
    rows = _cut(latex, "\\\\")
    if len(rows) > 1 and not rows[-1].strip():
        rows.pop()
    cells = [_cut(r, "&") for r in rows]
    if len(rows) > 1 or len(cells[0]) > 1:
        aligned = any(len(c) > 1 for c in cells)
        return _grid(sheet, cells, "aligned" if aligned else "gather", ("", ""))
    return _run(sheet, latex)


def _run(sheet: _Sheet, latex: str) -> _Box:
    """One line of math: text runs and environments side by side."""
    parts: list[_Box] = []
    rest = latex
    while True:
        env = _find_env(rest)
        if env is None:
            break
        start, end, name, body = env
        before, after = rest[:start], rest[end:]
        delims = _MATRIX.get(name, ("{", "") if name == "cases" else ("", ""))
        lm, rm = _LEFT.search(before), _RIGHT.search(after)
        if lm and rm:  # \left[ ... \right] around the block: drawn as its brackets
            before, after = before[:lm.start()], after[rm.end():]
            delims = (_DELIM_WORDS.get(lm.group(1), lm.group(1)), _DELIM_WORDS.get(rm.group(1), rm.group(1)))
        if before.strip():
            parts.append(_Text(sheet, f"${before}$"))
        parts.append(_env(sheet, name, body, delims))
        rest = after
    if rest.strip():
        parts.append(_Text(sheet, f"${rest}$"))
    if not parts:
        return _Box()
    return parts[0] if len(parts) == 1 else _Row(parts, gap=0.15 * sheet.em)


def _env(sheet: _Sheet, name: str, body: str, delims: tuple[str, str]) -> _Box:
    spec = None
    if name == "array":
        m = re.match(r"\s*\{([^{}]*)\}", body)
        if m:
            spec = [ch for ch in m.group(1) if ch in "lcr"] or None
            body = body[m.end():]
    elif name not in _MATRIX and name not in _ALIGNED and name not in _GATHER and name != "cases":
        raise ValueError(f"unknown environment {name}")
    rows = _cut(body, "\\\\")
    if len(rows) > 1 and not rows[-1].strip():
        rows.pop()
    cells = [_cut(r, "&") for r in rows]
    kind = "aligned" if name in _ALIGNED else "gather" if name in _GATHER else name
    return _grid(sheet, cells, kind, delims, spec)


def _grid(sheet: _Sheet, cells: list[list[str]], kind: str, delims: tuple[str, str], spec: list[str] | None = None) -> _Grid:
    em = sheet.em
    boxes = [[_math_box(sheet, c) if c.strip() else _Box() for c in r] for r in cells]
    if kind == "aligned":  # pairs of columns: the left one ends at the = sign, the right one starts there
        aligns, gaps, rowgap = ["r", "l"], [0.1 * em, 1.5 * em], 0.45 * em
    elif kind == "cases":
        aligns, gaps, rowgap = ["l"], [1.2 * em], 0.35 * em
    elif kind == "gather":
        aligns, gaps, rowgap = ["c"], [1.0 * em], 0.45 * em
    else:
        aligns, gaps, rowgap = spec or ["c"], [0.9 * em], 0.35 * em
    return _Grid(sheet, boxes, aligns, gaps, rowgap, delims)


def _draw(out: Path, text: str, size: float, dpi: int, display: bool = False) -> None:
    """Draw `text` (words with `$...$` math in them, or with `display`, one equation) to a PNG."""
    sheet = _Sheet(size, dpi)
    box: _Box
    pieces = split(text)
    if display:
        box = _math_box(sheet, text) if _needs_layout(text) else _Text(sheet, f"${_clean(text)}$")
    elif not any(_needs_layout(p) for kind, p in pieces if kind != "text"):
        # the common case: one run the typesetter draws whole, words and math together
        box = _Text(sheet, "".join(p if kind == "text" else f"${_clean(p)}$" for kind, p in pieces))
    else:
        parts: list[_Box] = []
        for kind, p in pieces:
            if kind == "text":
                if p.strip():
                    parts.append(_Text(sheet, p.replace("$", "\\$")))
                elif p:
                    parts.append(_Text(sheet, "\u00a0"))
            else:
                parts.append(_math_box(sheet, p))
        box = _Row(parts, gap=0.12 * sheet.em)
    pad = 0.03 * dpi
    sheet.fig.set_size_inches((box.w + 2 * pad) / dpi, (box.asc + box.desc + 2 * pad) / dpi)
    box.draw(pad, pad + box.desc)
    sheet.fig.savefig(out, dpi=dpi, transparent=True, format="png")
