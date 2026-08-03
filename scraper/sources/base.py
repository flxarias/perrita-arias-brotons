"""Contrato común de las fuentes."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..core.models import Dog

log = logging.getLogger("source")


@dataclass
class SourceResult:
    dogs: list[Dog] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pages: int = 0


class Source:
    """Una protectora o agregador.

    slug         identificador estable (entra en el id de cada perro)
    label        nombre legible
    kind         'agregador' | 'protectora'
    needs_browser  requiere renderizado JS (Playwright)
    """

    slug: str = ""
    label: str = ""
    home: str = ""
    kind: str = "protectora"
    needs_browser: bool = False
    provinces: list[str] = []
    enabled: bool = True

    def fetch(self, *, limit: int | None = None, incremental: bool = False) -> SourceResult:
        raise NotImplementedError

    # ------------------------------------------------------------------ utils
    def _result(self) -> SourceResult:
        return SourceResult()

    def log_error(self, res: SourceResult, msg: str) -> None:
        log.warning("[%s] %s", self.slug, msg)
        res.errors.append(msg)


REGISTRY: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    REGISTRY[cls.slug] = cls
    return cls
