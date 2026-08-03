"""Modelo canónico de una ficha de perro y su consolidación."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from . import normalize as N


@dataclass
class Dog:
    # --- identidad
    id: str = ""
    source: str = ""
    source_label: str = ""
    url: str = ""
    entry: str = "scraper"            # scraper | manual | link

    # --- ficha
    name: str = ""
    sex: str | None = None            # hembra | macho
    sex_inferred: bool = False
    birth_date: str | None = None     # YYYY-MM-DD
    age_months: int | None = None
    age_estimated: bool = False       # la edad viene de una categoría o del texto, no de una fecha
    age_band: str | None = None       # cachorro | joven | adulto | senior
    size: str | None = None           # mini | pequeno | mediano | grande | gigante
    size_inferred: bool = False
    weight_kg: float | None = None
    breed: str | None = None
    breed_type: str = "desconocido"   # raza | mezcla | mestizo | desconocido
    ppp: bool = False

    # --- localización y origen
    province: str | None = None
    location: str = ""
    shelter: str = ""
    shelter_url: str = ""
    shelter_kind: str = ""            # Protectora | Particular | Casa de acogida
    contact: str = ""

    # --- contenido
    photo: str = ""
    photos: list[str] = field(default_factory=list)
    description: str = ""
    traits: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)

    # --- estado y trazabilidad
    status: str = "disponible"
    urgent: bool = False
    first_seen: str = ""
    last_seen: str = ""
    updated_at: str = ""
    gone_since: str | None = None     # fecha en que dejó de aparecer en la fuente
    content_hash: str = ""

    # --- afinidad (lo calcula scoring.py)
    score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    def finalize(self) -> "Dog":
        """Rellena campos derivados y deja la ficha coherente."""
        self.name = N.clean_name(self.name) or "Sin nombre"
        self.description = N.clean_text(self.description)[:4000]

        if self.birth_date and self.age_months is None:
            self.age_months = N.months_since(self.birth_date)
        if self.age_months is not None:
            self.age_band = N.age_band(self.age_months)

        if not self.size:
            self.size = N.size_from_weight(self.weight_kg)
            if self.size:
                self.size_inferred = True
        if not self.size:
            self.size = N.size_from_breed(self.breed)
            if self.size:
                self.size_inferred = True

        if not self.sex:
            guessed = N.guess_sex_from_text(f"{self.name} {self.description}")
            if guessed:
                self.sex, self.sex_inferred = guessed, True

        self.ppp = N.is_ppp(self.breed)
        if not self.province:
            self.province = N.norm_province(self.location, f"{self.shelter} {self.description}")

        blob = f"{self.description} {' '.join(f'{k}' for k, v in self.traits.items() if v)}"
        self.traits = {**N.extract_flags(self.description, N.TRAIT_PATTERNS), **self.traits}
        self.health = {**N.extract_flags(self.description, N.HEALTH_PATTERNS), **self.health}

        if self.photos:
            self.photos = list(dict.fromkeys(p for p in self.photos if p))
            self.photo = self.photo or self.photos[0]
        elif self.photo:
            self.photos = [self.photo]

        if self.status == "urgente":
            self.urgent = True

        self.content_hash = self._hash()
        return self

    def _hash(self) -> str:
        parts = [
            self.name, self.sex or "", self.birth_date or "", str(self.age_months),
            self.size or "", self.breed or "", self.status, self.description[:600],
            self.photo,
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Dog":
        known = {f for f in Dog.__dataclass_fields__}
        return Dog(**{k: v for k, v in d.items() if k in known})


def make_id(source: str, native_id: str) -> str:
    return f"{source}:{N.slugify(native_id)[:64]}"


def dedupe_key(dog: Dog) -> str:
    """Clave heurística para detectar la misma perra publicada en dos portales."""
    bits = [
        N.key(dog.name),
        dog.sex or "?",
        dog.birth_date or (str(dog.age_months // 6) if dog.age_months is not None else "?"),
        dog.province or "?",
    ]
    return hashlib.sha1("|".join(bits).encode()).hexdigest()[:16]
