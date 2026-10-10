"""Saved pages: web pages the student keeps as starting points for everyday questions.

Dining hall hours, the gym's schedule, his church's events: things that change. Each saved page has a name, an
address, and a line about what it's for, which is how Claude knows where to start. Nothing is checked in the
background and nothing is kept in the vault. When he asks, Claude reads the page through Oso, which fetches it
right then like a plain download (no browser), and follows its links the same way as far as the answer needs. The
fetching has the rules of instructors' websites (`sites.py`): public addresses only, robots.txt honored, scripts
and navigation left out. A page that only fills in inside a browser, or needs a sign-in, is reported plainly, so
Claude can try another way, with a browser as the last resort.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

import requests

from . import config as cfgmod
from . import sites
from .config import Config, SavedPage

MAX_CHARS = 20_000  # a page's text, as Claude gets it
MAX_LINKS = 150
THIN = 200  # fewer readable characters than this, on a page with scripts, means it fills in inside a browser


def _find(cfg: Config, name: str) -> SavedPage | None:
    key = (name or "").strip().lower()
    return next((p for p in cfg.saved_pages if p.name.lower() == key), None)


def describe(cfg: Config) -> list[dict]:
    return [{"name": p.name, "about": p.about, "url": p.url} for p in cfg.saved_pages]


def save(cfg: Config, name: str, url: str, about: str) -> SavedPage:
    """Keep a page, or change the address or description of one with the same name. Raises ValueError."""
    name, about = " ".join((name or "").split())[:80], " ".join((about or "").split())[:300]
    if not name:
        raise ValueError("A saved page needs a name.")
    if not about:
        raise ValueError("A saved page needs a line about what it's for, so Claude knows when to look at it.")
    url = sites.normalize(url or "")
    page = _find(cfg, name)
    if page:
        page.url, page.about = url, about
    else:
        page = SavedPage(name=name, url=url, about=about)
        cfg.saved_pages.append(page)
    _keep(cfg)
    return page


def forget(cfg: Config, name: str) -> bool:
    page = _find(cfg, name)
    if page:
        cfg.saved_pages.remove(page)
        _keep(cfg)
    return page is not None


def _keep(cfg: Config) -> None:
    """Save the settings and list the pages in the vault's instructions right away, so the next chat knows them."""
    from . import instructions

    cfgmod.save(cfg)
    try:
        instructions.write(cfg)
    except OSError:
        pass  # the next check writes it


def read(cfg: Config, name: str | None = None, url: str | None = None, fetcher=None) -> dict | str:
    """A saved page (by name), or a page it leads to (by address), as it is right now: title, text, and links to
    follow. A sentence when it can't be read."""
    if url:
        try:
            url = sites.normalize(url)
        except ValueError as e:
            return str(e)
        label = url
    else:
        page = _find(cfg, name or "")
        if page is None:
            names = ", ".join(p.name for p in cfg.saved_pages) or "none yet"
            return f"No saved page called {name!r}. Saved pages: {names}."
        url, label = page.url, page.name
    fetcher = fetcher or sites._Fetcher()
    try:
        if not fetcher.allowed(url):
            return f"{label}: the site asks programs like Oso not to read that page."
        r = fetcher.get(url)
    except requests.RequestException:
        return f"{label}: Oso couldn't reach the page."
    kind = (r.headers.get("Content-Type") or "").lower()
    if kind and "html" not in kind and not kind.startswith("text/") and "json" not in kind:
        return f"{label}: the address isn't a web page Oso can read."
    body = r.text
    if sites._looks_like_sign_in(r, body if "html" in kind or not kind else ""):
        return f"{label}: the page needs a sign-in, which Oso can't do."
    if r.status_code >= 400:
        return f"{label}: the page didn't load (the site answered {r.status_code})."
    links: list[dict] = []
    if "html" in kind or not kind:
        parsed = sites.parse(body)
        text, title = parsed.text(), " ".join(parsed.title.split())
        if len(text) < THIN and parsed.scripts:
            return f"{label}: the page only fills in inside a browser, so Oso can't read it."
        seen = set()
        for href, words in parsed.links:
            target = urljoin(r.url, href).split("#")[0]
            if target.startswith(("http://", "https://")) and target not in seen and target != r.url:
                seen.add(target)
                links.append({"text": words[:80], "url": target})
    else:
        text, title = body.strip(), ""
    return {"url": r.url, "title": title or label, "read_at": datetime.now().astimezone().isoformat(timespec="minutes"),
            "text": text[:MAX_CHARS] + ("\n\n[The rest of the page was cut.]" if len(text) > MAX_CHARS else ""),
            "links": links[:MAX_LINKS]}
