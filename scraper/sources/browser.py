"""Scrapeado "a mano" con navegador real (Playwright).

Necesario para las protectoras montadas sobre Wix/React, donde el HTML que
llega por HTTP viene vacío, y para los perfiles públicos de redes sociales.
Si Playwright no está instalado, todo el módulo degrada a None y el resto del
barrido sigue funcionando: es una mejora, nunca un requisito.

    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import logging
import re
import time

log = logging.getLogger("browser")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except Exception:
        return False


class Browser:
    """Contexto de navegador reutilizable durante un barrido."""

    def __init__(self, headless: bool = True, locale: str = "es-ES"):
        self.headless = headless
        self.locale = locale
        self._pw = None
        self._browser = None
        self._ctx = None

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._ctx = self._browser.new_context(
            user_agent=_UA,
            locale=self.locale,
            viewport={"width": 1366, "height": 900},
            java_script_enabled=True,
        )
        self._ctx.set_default_timeout(30_000)
        return self

    def __exit__(self, *exc) -> None:
        for obj in (self._ctx, self._browser):
            try:
                obj and obj.close()
            except Exception:
                pass
        try:
            self._pw and self._pw.stop()
        except Exception:
            pass

    def html(self, url: str, *, wait_selector: str | None = None, scroll: int = 0) -> str:
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            self._dismiss_cookies(page)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=12_000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(1800)
            for _ in range(scroll):
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(900)
            return page.content()
        finally:
            page.close()

    @staticmethod
    def _dismiss_cookies(page) -> None:
        """Rechaza el banner de cookies eligiendo siempre la opción más restrictiva."""
        for pattern in (
            r"rechazar todas", r"solo (las )?necesarias", r"rechazar", r"denegar", r"reject all",
        ):
            try:
                btn = page.get_by_role("button", name=re.compile(pattern, re.I)).first
                if btn.is_visible(timeout=1200):
                    btn.click(timeout=2500)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue


def render(url: str, *, wait_selector: str | None = None, scroll: int = 0) -> str | None:
    """Devuelve el HTML ya renderizado, o None si Playwright no está disponible."""
    if not available():
        log.info("Playwright no disponible; se omite el renderizado de %s", url)
        return None
    try:
        with Browser() as b:
            return b.html(url, wait_selector=wait_selector, scroll=scroll)
    except Exception as exc:
        log.warning("fallo al renderizar %s: %s", url, exc)
        return None


def render_many(urls: list[str], *, wait_selector: str | None = None, scroll: int = 0) -> dict[str, str]:
    """Renderiza varias URLs reutilizando un único navegador (mucho más rápido)."""
    out: dict[str, str] = {}
    if not available() or not urls:
        return out
    try:
        with Browser() as b:
            for u in urls:
                try:
                    out[u] = b.html(u, wait_selector=wait_selector, scroll=scroll)
                except Exception as exc:
                    log.warning("fallo en %s: %s", u, exc)
                time.sleep(0.4)
    except Exception as exc:
        log.warning("no se pudo abrir el navegador: %s", exc)
    return out
