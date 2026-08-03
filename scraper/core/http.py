"""Cliente HTTP compartido: sesión con reintentos, cortesía y caché opcional en disco."""
from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("http")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CACHE_DIR = Path(os.environ.get("PAB_CACHE_DIR", ".cache/http"))
CACHE_TTL = int(os.environ.get("PAB_CACHE_TTL", "0"))  # segundos; 0 = sin caché


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    retry = Retry(
        total=3,
        backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


SESSION = _session()

_last_hit: dict[str, float] = {}
MIN_INTERVAL = float(os.environ.get("PAB_MIN_INTERVAL", "0.6"))


def _polite(url: str) -> None:
    """Espacia las peticiones por dominio para no castigar servidores pequeños."""
    host = url.split("/")[2] if "://" in url else url
    now = time.monotonic()
    prev = _last_hit.get(host)
    if prev is not None:
        wait = MIN_INTERVAL - (now - prev)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.25))
    _last_hit[host] = time.monotonic()


def _cache_path(url: str, body: str = "") -> Path:
    key = hashlib.sha256((url + "|" + body).encode()).hexdigest()[:32]
    return CACHE_DIR / f"{key}.html"


def get(url: str, *, session: requests.Session | None = None, timeout: int = 30, **kw) -> requests.Response:
    sess = session or SESSION
    if CACHE_TTL:
        p = _cache_path(url)
        if p.exists() and time.time() - p.stat().st_mtime < CACHE_TTL:
            r = requests.Response()
            r._content = p.read_bytes()
            r.status_code = 200
            r.url = url
            r.encoding = "utf-8"
            return r
    _polite(url)
    r = sess.get(url, timeout=timeout, **kw)
    if CACHE_TTL and r.ok:
        p = _cache_path(url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
    return r


def post(url: str, *, session: requests.Session | None = None, timeout: int = 30, **kw) -> requests.Response:
    sess = session or SESSION
    _polite(url)
    return sess.post(url, timeout=timeout, **kw)


def get_json(url: str, **kw):
    r = get(url, **kw)
    r.raise_for_status()
    return r.json()


def soup(url_or_html: str, *, is_html: bool = False, **kw):
    from bs4 import BeautifulSoup

    if is_html:
        return BeautifulSoup(url_or_html, "lxml")
    r = get(url_or_html, **kw)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return BeautifulSoup(r.text, "lxml")
