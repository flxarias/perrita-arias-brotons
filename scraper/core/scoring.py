"""Afinidad con lo que busca la familia Arias Brotóns.

Devuelve 0-100 y el desglose, para que la web pueda explicar *por qué* una
perrita encaja. Todo sale de config/criteria.json: cambiar los pesos ahí
recalcula el ranking sin tocar código.
"""
from __future__ import annotations

from .models import Dog
from .normalize import SIZE_ORDER, geo_tier

TIER_SCORE = {"core": 1.0, "near": 0.72, "east": 0.42, "far": 0.10, "desconocido": 0.30}


def _age_fit(age_months: int | None, ideal_max: int, acceptable_max: int) -> tuple[float, str]:
    if age_months is None:
        return 0.35, "edad sin confirmar"
    if age_months <= ideal_max:
        return 1.0, f"{age_months} meses — cachorra"
    if age_months <= acceptable_max:
        span = max(1, acceptable_max - ideal_max)
        v = 1.0 - 0.4 * (age_months - ideal_max) / span
        return v, f"{age_months} meses — muy joven"
    if age_months <= 36:
        return 0.35, f"{age_months} meses — joven"
    if age_months <= 84:
        return 0.12, "adulta"
    return 0.04, "senior"


def _size_fit(size: str | None, preferred: list[str]) -> tuple[float, str]:
    if not size:
        return 0.35, "tamaño sin confirmar"
    if size in preferred:
        return 1.0, f"tamaño {size}"
    # penalización proporcional a la distancia respecto al mayor tamaño aceptado
    try:
        worst_ok = max(SIZE_ORDER.index(s) for s in preferred if s in SIZE_ORDER)
        dist = SIZE_ORDER.index(size) - worst_ok
    except ValueError:
        return 0.3, f"tamaño {size}"
    return max(0.0, 0.45 - 0.2 * max(0, dist)), f"tamaño {size}"


def _breed_fit(breed_type: str) -> tuple[float, str]:
    return {
        "raza": (1.0, "de raza"),
        "mezcla": (0.85, "mezcla identificada"),
        "mestizo": (0.55, "mestiza"),
        "desconocido": (0.4, "raza sin confirmar"),
    }[breed_type]


def score_dog(dog: Dog, criteria: dict) -> Dog:
    t = criteria["target"]
    w = criteria["weights"]
    reasons: dict[str, dict] = {}
    flags: list[str] = []

    # --- sexo
    if dog.sex == t["sex"]:
        sex_v, sex_txt = (0.85 if dog.sex_inferred else 1.0), "hembra"
    elif dog.sex is None:
        sex_v, sex_txt = 0.25, "sexo sin confirmar"
    else:
        sex_v, sex_txt = 0.0, "macho"
    reasons["sexo"] = {"value": round(sex_v, 2), "weight": w["sex"], "text": sex_txt}

    # --- edad
    age_v, age_txt = _age_fit(dog.age_months, t["age_months_ideal_max"], t["age_months_acceptable_max"])
    reasons["edad"] = {"value": round(age_v, 2), "weight": w["age"], "text": age_txt}

    # --- tamaño
    size_v, size_txt = _size_fit(dog.size, t["sizes_preferred"])
    reasons["tamaño"] = {"value": round(size_v, 2), "weight": w["size"], "text": size_txt}

    # --- geografía
    tier = geo_tier(dog.province, criteria)
    geo_v = TIER_SCORE[tier]
    reasons["zona"] = {
        "value": round(geo_v, 2), "weight": w["geo"],
        "text": dog.province or "zona sin confirmar", "tier": tier,
    }

    # --- raza
    breed_v, breed_txt = _breed_fit(dog.breed_type)
    reasons["raza"] = {"value": round(breed_v, 2), "weight": w["breed"], "text": breed_txt}

    # --- convivencia con niñas
    kids = dog.traits.get("good_with_kids")
    if kids is True:
        kids_v, kids_txt = 1.0, "buena con niños"
    elif kids is False:
        kids_v, kids_txt = 0.0, "no apta para niños"
        flags.append("no-ninos")
    else:
        kids_v, kids_txt = 0.5, "convivencia con niños sin confirmar"
    reasons["niñas"] = {"value": round(kids_v, 2), "weight": w["kids"], "text": kids_txt}

    total_w = sum(w.values())
    raw = sum(r["value"] * r["weight"] for r in reasons.values()) / total_w
    score = raw * 100

    # --- penalizaciones y descartes
    if dog.ppp and t.get("exclude_ppp"):
        score *= 0.25
        flags.append("ppp")
    if dog.status in ("adoptado", "reservado"):
        score *= 0.15 if dog.status == "adoptado" else 0.6
        flags.append(dog.status)
    if tier == "far":
        flags.append("fuera-de-zona")
    if dog.urgent:
        score = min(100, score * 1.05)
        flags.append("urgente")
    if not dog.photo:
        score *= 0.95
        flags.append("sin-foto")

    dog.score = int(round(max(0, min(100, score))))
    dog.score_breakdown = reasons
    dog.flags = flags
    return dog


def is_notifiable(dog: Dog, criteria: dict) -> bool:
    n = criteria["notify"]
    if dog.status in ("adoptado", "reservado"):
        return False
    if dog.ppp and criteria["target"].get("exclude_ppp"):
        return False
    always = n["always_notify_if"]
    tier = geo_tier(dog.province, criteria)
    if (
        dog.sex == always["sex"]
        and dog.age_months is not None
        and dog.age_months <= always["age_months_max"]
        and (dog.size in always["sizes"] or dog.size is None)
        and tier in always["tiers"]
    ):
        return True
    return dog.score >= n["min_score"]
