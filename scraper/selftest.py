"""Comprobaciones rápidas de los normalizadores y del cálculo de afinidad.

No toca la red: son los casos reales que ya han roto el parser alguna vez.

    python -m scraper.selftest
"""
from __future__ import annotations

import sys

from .core import normalize as N
from .core.models import Dog
from .core.scoring import is_notifiable, score_dog
from .core.store import load_criteria

FAILS: list[str] = []


def eq(got, want, label):
    if got != want:
        FAILS.append(f"{label}: esperaba {want!r}, obtuve {got!r}")


def run() -> int:
    # --- sexo
    eq(N.norm_sex("Hembra"), "hembra", "sexo hembra")
    eq(N.norm_sex("MACHO"), "macho", "sexo macho")
    eq(N.norm_sex("Desconocido"), None, "sexo desconocido")

    # --- edad: el texto de la ficha manda sobre las categorías
    eq(N.parse_age_months("2 años 2 meses"), 26, "edad años+meses")
    eq(N.parse_age_months("13 años 8 meses"), 164, "edad senior")
    eq(N.parse_age_months("8 meses"), 8, "edad meses")
    eq(N.parse_age_months("Cachorro"), 6, "edad por categoría")
    eq(N.parse_age_months("Cachorro", with_flag=True)[1], True, "categoría marcada como estimación")
    eq(N.parse_age_months("6 semanas"), 1, "edad semanas")
    eq(N.parse_age_months("año y medio"), 18, "año y medio")
    # el dominio de Las Reinas del Biberón no es una edad
    eq(N.parse_age_months("paypal.me/lasreinasdelbiberon 644 21 90 01"), None, "URL no es edad")
    eq(N.parse_age_months("Bizum ONG: 03760"), None, "teléfono no es edad")

    # --- fechas
    eq(N.parse_birth_date("01-06-2024"), "2024-06-01", "fecha dd-mm-yyyy")
    eq(N.parse_birth_date("08.09.2024"), "2024-09-08", "fecha dd.mm.yyyy")
    eq(N.parse_birth_date("2021-03-10"), "2021-03-10", "fecha iso")
    eq(N.parse_birth_date("no hay fecha"), None, "sin fecha")

    # --- tamaño
    eq(N.norm_size("Pequeño"), "pequeno", "tamaño pequeño")
    eq(N.norm_size("Desconocido"), None, "tamaño desconocido")
    eq(N.size_from_weight(20), "mediano", "20 kg → mediano")
    eq(N.size_from_weight(25), "grande", "25 kg → grande")
    eq(N.size_from_weight(3.5), "mini", "3,5 kg → mini")
    eq(N.parse_weight("19.5 kg"), 19.5, "peso decimal")
    eq(N.parse_weight(" kg"), None, "peso vacío")

    # --- razas
    eq(N.norm_breed("Mestizo")[1], "mestizo", "mestizo")
    eq(N.norm_breed("Mestizo de American Staffordshire Terrier")[1], "mezcla", "mezcla")
    eq(N.is_ppp("Mestizo de American Staffordshire Terrier"), True, "PPP detectada")
    eq(N.is_ppp("Mezcla de Bodeguero"), False, "no PPP")
    eq(N.size_from_breed("Chihuahua"), "mini", "tamaño por raza")
    eq(N.looks_like_cat("Común Europeo"), True, "gato por raza")
    eq(N.looks_like_cat("Podenco", "Camelia", "se lleva bien con gatos"), False,
       "convivir con gatos no la convierte en gata")

    # --- geografía
    eq(N.norm_province("Callosa de Segura"), "Alicante", "municipio → provincia")
    eq(N.norm_province("Alicante, España"), "Alicante", "provincia directa")
    eq(N.norm_province("Cartagena"), "Murcia", "Cartagena → Murcia")
    eq(N.norm_province("Ninguna parte"), None, "sin provincia")

    # --- rasgos
    flags = N.extract_flags("Es muy cariñosa y buena con niños", N.TRAIT_PATTERNS)
    eq(flags.get("good_with_kids"), True, "buena con niños")
    eq(flags.get("affectionate"), True, "cariñosa")

    # --- afinidad
    criteria = load_criteria()
    ideal = Dog(
        id="t:1", name="Prueba", sex="hembra", age_months=4, size="pequeno",
        breed="Mezcla de Bretón", breed_type="mezcla", province="Alicante",
        traits={"good_with_kids": True},
    ).finalize()
    score_dog(ideal, criteria)
    if ideal.score < 90:
        FAILS.append(f"afinidad ideal: esperaba ≥90, obtuve {ideal.score}")
    eq(is_notifiable(ideal, criteria), True, "la ideal se notifica")

    lejos = Dog(
        id="t:2", name="Lejos", sex="macho", age_months=96, size="gigante",
        breed="Mastín Español", breed_type="raza", province="A Coruña",
    ).finalize()
    score_dog(lejos, criteria)
    if lejos.score > 30:
        FAILS.append(f"afinidad lejana: esperaba ≤30, obtuve {lejos.score}")
    eq(is_notifiable(lejos, criteria), False, "la lejana no se notifica")

    ppp = Dog(
        id="t:3", name="PPP", sex="hembra", age_months=5, size="mediano",
        breed="American Staffordshire Terrier", breed_type="raza", province="Alicante",
    ).finalize()
    score_dog(ppp, criteria)
    eq(ppp.ppp, True, "PPP marcada")
    eq(is_notifiable(ppp, criteria), False, "PPP no se notifica")

    # --- derivados de la ficha
    d = Dog(id="t:4", name="  luna  ", birth_date="2026-02-01", weight_kg=8,
            description="Es una perrita muy juguetona, vacunada y con microchip.").finalize()
    eq(d.name, "Luna", "nombre limpio")
    eq(d.size, "pequeno", "tamaño inferido del peso")
    eq(d.size_inferred, True, "tamaño marcado como inferido")
    eq(d.health.get("vaccinated"), True, "vacunada desde el texto")
    eq(d.age_band, "cachorro", "banda de edad")

    print(f"{'FALLOS' if FAILS else 'OK'} — {len(FAILS)} problemas")
    for f in FAILS:
        print("  ✗", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(run())
