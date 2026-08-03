"""Registro de fuentes: adaptadores propios + fuentes declarativas."""
from __future__ import annotations

from .base import REGISTRY, Source
from . import apadac, kerubi, miwuki, woocommerce  # noqa: F401  (registran al importarse)
from .site import load_site_sources


def build_sources(selected: list[str] | None = None, *, use_browser: bool = True) -> list[Source]:
    sources: list[Source] = [cls() for cls in REGISTRY.values()]
    sources += load_site_sources()
    if not use_browser:
        sources = [s for s in sources if not s.needs_browser]
    if selected:
        wanted = {s.lower() for s in selected}
        sources = [s for s in sources if s.slug.lower() in wanted]
    return [s for s in sources if s.enabled]
