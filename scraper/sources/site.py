"""Fuentes declarativas: una protectora nueva se añade editando config/sources.json.

Cada entrada describe dónde está el listado y cómo se reconoce el enlace a una
ficha; el resto lo resuelve el extractor genérico. Cuando la web es JS (Wix,
React) basta con marcar "browser": true y se renderiza con Playwright.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..core import normalize as N
from ..core.http import get
from ..core.models import Dog
from .base import Source, SourceResult
from .generic import extract_from_html

CONFIG = Path(__file__).resolve().parents[2] / "config" / "sources.json"


class SiteSource(Source):
    def __init__(self, spec: dict):
        self.spec = spec
        self.slug = spec["slug"]
        self.label = spec["label"]
        self.home = spec.get("home", "")
        self.kind = spec.get("kind", "protectora")
        self.needs_browser = bool(spec.get("browser"))
        self.provinces = spec.get("provinces", [])
        self.enabled = spec.get("enabled", True)
        self.default_province = spec.get("province")
        self.detail_re = re.compile(spec["detail_pattern"])
        self.exclude_re = re.compile(spec["exclude_pattern"]) if spec.get("exclude_pattern") else None
        self.listings = spec.get("listings", [])
        self.max_details = int(spec.get("max_details", 120))
        self.wait_selector = spec.get("wait_selector")
        self.name_selector = spec.get("name_selector")
        self.scroll = int(spec.get("scroll", 0))

    # ------------------------------------------------------------------ html
    def _html(self, url: str, browser) -> str:
        if self.needs_browser and browser is not None:
            html = browser.html(url, wait_selector=self.wait_selector, scroll=self.scroll)
            if html:
                return html
        r = get(url)
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text

    def _detail_links(self, listing: str, html: str) -> list[str]:
        s = BeautifulSoup(html, "lxml")
        out = []
        for a in s.select("a[href]"):
            href = urljoin(listing, a["href"])
            if urlparse(href).netloc != urlparse(listing).netloc:
                continue
            if not self.detail_re.search(href):
                continue
            if self.exclude_re and self.exclude_re.search(href):
                continue
            out.append(href.split("#")[0])
        return list(dict.fromkeys(out))

    # ------------------------------------------------------------------ api
    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        res = self._result()
        browser = None
        ctx = None
        if self.needs_browser:
            from .browser import Browser, available

            if available():
                ctx = Browser()
                browser = ctx.__enter__()
            else:
                self.log_error(res, "requiere Playwright y no está instalado")

        try:
            links: list[str] = []
            for listing in self.listings:
                try:
                    html = self._html(listing, browser)
                    res.pages += 1
                    links += self._detail_links(listing, html)
                except Exception as exc:
                    self.log_error(res, f"listado {listing}: {exc}")

            links = list(dict.fromkeys(links))[: (limit or self.max_details)]
            for url in links:
                try:
                    html = self._html(url, browser)
                    dog = extract_from_html(
                        html, url, source=self.slug, label=self.label,
                        name_selector=self.name_selector,
                    )
                    dog = self._postprocess(dog)
                    if dog:
                        res.dogs.append(dog)
                except Exception as exc:
                    self.log_error(res, f"ficha {url}: {exc}")
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
        return res

    def _postprocess(self, dog: Dog) -> Dog | None:
        if N.looks_like_cat(dog.breed, dog.name, dog.description[:300]):
            return None
        if N.looks_like_listing(dog.name):
            return None
        if not dog.province and self.default_province:
            dog.province = self.default_province
            dog.location = dog.location or self.default_province
        if not dog.shelter or dog.shelter.startswith(urlparse(self.home).netloc.replace("www.", "")):
            dog.shelter = self.label
        dog.shelter_url = dog.shelter_url or self.home
        return dog.finalize()


def load_site_sources() -> list[SiteSource]:
    if not CONFIG.exists():
        return []
    specs = json.loads(CONFIG.read_text(encoding="utf-8"))["sources"]
    return [SiteSource(s) for s in specs if s.get("enabled", True)]
