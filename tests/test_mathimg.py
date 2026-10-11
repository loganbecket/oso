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
    assert mathimg.render("$\\begin{tikzpicture} x \\end{tikzpicture}$", size=13, dpi=110) is None
    assert mathimg.render("$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4$", size=13, dpi=110) is None  # no \\end
    assert not list(tmp_path.glob("math/*.part"))


def test_matrices_cases_and_derivations_are_drawn(tmp_path: Path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path)

    def size_of(latex: str, display: bool = True) -> tuple[int, int]:
        out = mathimg.render(latex, size=13, dpi=110, display=display)
        assert out is not None, latex
        with Image.open(out) as im:
            return im.size

    one = size_of("x = 1")
    matrix = size_of("A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}")
    tall = size_of("\\begin{bmatrix} x_1 \\\\ x_2 \\\\ x_3 \\end{bmatrix}")
    assert matrix[1] > 1.6 * one[1] and tall[1] > matrix[1]  # two rows, then three
    derivation = size_of("\\begin{aligned} F &= ma \\\\ &= (2\\,\\text{kg})(3\\,\\text{m/s}^2) \\\\ &= 6\\,\\text{N} \\end{aligned}")
    assert derivation[1] > 2.5 * one[1]
    assert size_of("a &= b \\\\ c &= d")[1] > 1.6 * one[1]  # line breaks without an environment still stack
    assert size_of("f(x) = \\begin{cases} x^2 & \\text{if } x \\ge 0 \\\\ -x & \\text{otherwise} \\end{cases}")[1] > 1.6 * one[1]
    assert size_of("\\left[ \\begin{array}{cc} 1 & 0 \\\\ 0 & 1 \\end{array} \\right] \\vec v = \\vec v")[1] > 1.6 * one[1]
    assert size_of("\\begin{bmatrix} \\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix} & 0 \\\\ 0 & 1 \\end{bmatrix}")[1] > tall[1]  # nested
    # the commands the typesetter lacks are swapped for ones it has
    assert size_of("x \\le 1, y \\ne 2, z \\ge 3 \\implies \\dfrac{a}{b} \\text{ for all } x")[0] > one[0]
    # a line of words with a matrix in it, for a choice
    assert mathimg.picture("The inverse is $\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}^{-1}$ here", size=11, dpi=110) is not None


def test_cutting_rows_and_cells_respects_nesting():
    assert mathimg._cut("a & b \\\\ c & d", "\\\\") == ["a & b ", " c & d"]
    assert mathimg._cut("\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix} & x", "\\\\") == ["\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix} & x"]
    assert mathimg._cut("\\frac{a & b}{c} & d", "&") == ["\\frac{a & b}{c} ", " d"]
    assert mathimg._find_env("x = \\begin{bmatrix} \\begin{pmatrix} 1 \\end{pmatrix} \\end{bmatrix} + 1") == (
        4, 65, "bmatrix", " \\begin{pmatrix} 1 \\end{pmatrix} ")
    assert mathimg._clean("\\text{if } x \\\\[4pt] \\displaystyle y \\dfrac{1}{2}") == "\\mathrm{if\\ } x \\\\  y \\frac{1}{2}"
