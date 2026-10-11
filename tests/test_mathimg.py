"""Equations in the quiz window: splitting text from LaTeX, and drawing each equation as a picture."""

from pathlib import Path

from oso import config as cfgmod
from oso import mathimg


def test_text_is_split_around_inline_and_display_math():
    text = "Find $\\int_0^1 x\\,dx$ when\n$$F = ma$$\nand it costs $5 and $6."
    assert mathimg.split(text) == [
        ("text", "Find "), ("inline", "\\int_0^1 x\\,dx"), ("text", " when\n"), ("display", "F = ma"),
        ("text", "\nand it costs $5 and $6."),
    ]
    assert mathimg.has_math("the ratio $v^2/r$") and not mathimg.has_math("$5 and $6") and not mathimg.has_math(None)
    assert mathimg.split("no math") == [("text", "no math")]


def test_an_equation_becomes_a_picture_once(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path)
    out = mathimg.render("$\\frac{\\pi^2}{6} = \\sum_{n=1}^{\\infty} \\frac{1}{n^2}$", size=13, dpi=110)
    assert out is not None and out.suffix == ".png" and out.stat().st_size > 500 and out.read_bytes()[:4] == b"\x89PNG"
    first = out.stat().st_mtime_ns
    assert mathimg.render("$\\frac{\\pi^2}{6} = \\sum_{n=1}^{\\infty} \\frac{1}{n^2}$", size=13, dpi=110) == out
    assert out.stat().st_mtime_ns == first  # drawn once, then reused
    assert mathimg.picture("The ratio $\\frac{v^2}{r}$ here", size=11, dpi=110) is not None
    assert not list(tmp_path.glob("math/*.part"))


def test_a_formula_that_cannot_be_drawn_is_left_as_written(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path)
    assert mathimg.render("$\\frac{1}{$", size=13, dpi=110) is None
    assert mathimg.render("$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$", size=13, dpi=110) is None
