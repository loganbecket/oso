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
            import winrt.windows.media.ocr  # noqa: F401
            return True
        if sys.platform == "darwin":
            import Vision  # noqa: F401
            return True
    except Exception:  # noqa: BLE001
        return False
    return shutil.which("tesseract") is not None


def read_image(path: Path) -> str:
    """The text on one page image."""
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
