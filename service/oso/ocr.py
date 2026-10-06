"""Text recognition for scanned pages, using what the operating system already has.

Windows 10 and 11 include a text recognizer (Windows.Media.Ocr) and macOS includes one (the Vision
framework); Oso calls whichever is there, on the laptop, so a scanned book costs no Claude usage. On Linux
the free `tesseract` program is used if it is installed. Recognition is weak on equations and diagrams, so
each page also gets a rough quality judgment: pages that come out poorly are flagged for Claude to read
from the page image when he first asks about them.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("oso.ocr")


class OcrUnavailable(Exception):
    """No text recognizer on this computer."""


def available() -> bool:
    try:
        if sys.platform == "win32":
            import importlib.util

            return importlib.util.find_spec("winrt.windows.media.ocr") is not None  # checked without loading it
        if sys.platform == "darwin":
            import Vision  # noqa: F401
            return True
    except Exception:  # noqa: BLE001
        return False
    return shutil.which("tesseract") is not None


def read_image(path: Path) -> str:
    """The text on one page image."""
    return read_images([path])[0]


def read_images(paths: list[Path]) -> list[str]:
    """The text on several page images. On Windows the recognizer runs in a separate process: loaded in the
    same process as the search model (ONNX Runtime), it crashes Python."""
    if not paths:
        return []
    if sys.platform == "win32":
        import json

        r = subprocess.run([sys.executable, "-m", "oso.ocr", *map(str, paths)], capture_output=True, text=True, encoding="utf-8",
                           timeout=60 + 30 * len(paths), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            why = (r.stderr or "").strip().splitlines()[-1:] or ["unknown reason"]
            raise OcrUnavailable(f"Windows text recognition is not available ({why[0][:160]}).")
        return json.loads(r.stdout)
    return [_read_here(p) for p in paths]


def _read_here(path: Path) -> str:
    if sys.platform == "win32":
        return _windows(path)
    if sys.platform == "darwin":
        return _macos(path)
    if shutil.which("tesseract"):
        r = subprocess.run(["tesseract", str(path), "-", "--psm", "3"], capture_output=True, text=True, timeout=120)
        return r.stdout
    raise OcrUnavailable("This computer has no text recognizer for scanned pages.")


def _windows(path: Path) -> str:
    try:
        import asyncio

        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile
    except Exception as e:  # noqa: BLE001
        raise OcrUnavailable("Windows text recognition is not available.") from e

    async def run() -> str:
        f = await StorageFile.get_file_from_path_async(str(path.resolve()))
        stream = await f.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise OcrUnavailable("Windows has no text recognition language installed.")
        result = await engine.recognize_async(bitmap)
        return "\n".join(line.text for line in result.lines)

    return asyncio.run(run())


def _macos(path: Path) -> str:
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except Exception as e:  # noqa: BLE001
        raise OcrUnavailable("macOS text recognition is not available.") from e
    url = NSURL.fileURLWithPath_(str(path.resolve()))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    handler.performRequests_error_([request], None)
    lines = []
    for obs in request.results() or []:
        top = obs.topCandidates_(1)
        if top:
            lines.append(str(top[0].string()))
    return "\n".join(lines)


def poor(text: str) -> bool:
    """A rough judgment that recognition went badly: very little text, or mostly symbols rather than words
    (typical of equations, tables, and figures). Those pages are worth Claude reading from the image."""
    stripped = text.strip()
    if len(stripped) < 120:
        return True
    words = re.findall(r"[A-Za-z]{3,}", stripped)
    letters = sum(len(w) for w in words)
    return letters / max(1, len(re.sub(r"\s", "", stripped))) < 0.55


if __name__ == "__main__":  # the Windows worker: page images in, their text out as JSON
    import json

    try:
        print(json.dumps([_read_here(Path(p)) for p in sys.argv[1:]]))
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
