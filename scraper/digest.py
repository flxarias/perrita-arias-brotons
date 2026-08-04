"""Resumen matinal por correo, a las 07:00 hora de Madrid.

No barre nada: lee la base de datos que dejó el barrido de las 00:00 y cuenta
qué ha aparecido desde el último envío. Guarda la marca en data/meta.json, así
que no repite fichas ni se salta ninguna aunque un día falle el envío o se
añada algo a mano por la tarde.

    python -m scraper.digest            # envía
    python -m scraper.digest --preview  # solo escribe el HTML, no envía
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import store
from .core.normalize import now_iso
from .core.scoring import is_notifiable
from .notify import SITE, SIZE_LABEL, _link, _meta, recipients, send_mail

DISPONIBLES = ("disponible", "urgente", "acogida")


# --------------------------------------------------------------------------- datos

def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect() -> dict:
    raw = json.loads(store.DOGS_JSON.read_text(encoding="utf-8"))
    dogs = raw["dogs"]
    meta = store.load_meta()
    criteria = store.load_criteria()

    since = _parse(meta.get("last_digest_sent")) or datetime.now(timezone.utc) - timedelta(days=1)

    def as_item(d: dict) -> dict:
        return {
            "id": d["id"], "name": d["name"], "score": d["score"], "url": d["url"],
            "sex": d.get("sex"), "age_months": d.get("age_months"), "size": d.get("size"),
            "province": d.get("province"), "shelter": d.get("shelter") or d.get("source_label"),
            "photo": d.get("photo"), "breed": d.get("breed"),
        }

    from .core.models import Dog

    # Todas las altas desde el último envío. La criba por afinidad solo se usa
    # ya para marcar cuáles encajan, no para esconder ninguna.
    nuevas = []
    for d in dogs:
        first = _parse(d.get("first_seen"))
        if first and first > since and d.get("status") in DISPONIBLES:
            item = as_item(d)
            item["encaja"] = is_notifiable(Dog.from_dict(d), criteria)
            nuevas.append(item)
    nuevas.sort(key=lambda d: (-int(d["encaja"]), -d["score"]))

    vivas = [d for d in dogs if d.get("status") in DISPONIBLES and not d.get("ppp")]

    return {
        "at": now_iso(),
        "since": since.isoformat(),
        "generated_at": raw.get("generated_at"),
        "total": len(dogs),
        "vivas": len(vivas),
        "alicante": sum(1 for d in vivas if d.get("province") == "Alicante"),
        "cachorras": sum(1 for d in vivas if d.get("sex") == "hembra" and (d.get("age_months") or 999) <= 12),
        "nuevas": nuevas,
        "salud": meta.get("source_health", {}),
    }


# --------------------------------------------------------------------------- correo

def _card(d: dict) -> str:
    photo = d.get("photo") or ""
    marca = (
        '<span style="background:#e7f0e9;color:#3f7d52;border-radius:999px;'
        'padding:2px 8px;font-size:11px;font-weight:700;margin-left:6px">ENCAJA</span>'
        if d.get("encaja") else ""
    )
    img = (
        f'<img src="{photo}" width="92" height="92" alt="" '
        f'style="border-radius:16px;object-fit:cover;display:block">'
        if photo else '<div style="width:92px;height:92px;border-radius:16px;background:#f0e9df"></div>'
    )
    return f"""
<tr>
  <td style="padding:10px 0;vertical-align:top;width:106px">{img}</td>
  <td style="padding:10px 0;vertical-align:top;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1c1815">
    <a href="{_link(d)}" style="color:#c4562f;text-decoration:none;font-size:18px;font-weight:600">{d['name']}</a>
    <span style="background:#fbeae2;color:#c4562f;border-radius:999px;padding:2px 9px;font-size:12px;font-weight:700;margin-left:6px">{d['score']}</span>{marca}
    <div style="color:#8b8076;font-size:13px;margin-top:3px">{_meta(d)}</div>
    <div style="color:#4b423a;font-size:13px">{d.get('breed') or ''}{' · ' if d.get('breed') and d.get('shelter') else ''}{d.get('shelter') or ''}</div>
  </td>
</tr>"""


# El runner de GitHub va en inglés y `locale` no siempre está disponible, así
# que los meses se escriben aquí y no se depende del sistema.
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(d: datetime) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def build_html(data: dict) -> str:
    hoy = fecha_larga(datetime.now(timezone.utc) + timedelta(hours=2))
    n = len(data["nuevas"])

    # Solo las altas del día: todas, sin recortar y sin bloques de relleno.
    if n:
        encajan = sum(1 for d in data["nuevas"] if d.get("encaja"))
        titulo = f"{n} novedad{'es' if n != 1 else ''} publicada{'s' if n != 1 else ''}"
        bloque = (
            f'<p style="margin:0 0 14px;color:#8b8076;font:14px sans-serif">'
            f'{encajan} encaja{"n" if encajan != 1 else ""} con lo que buscáis.</p>'
            f'<table style="width:100%;border-collapse:collapse">'
            f'{"".join(_card(d) for d in data["nuevas"])}</table>'
        )
    else:
        titulo = "Hoy no hay novedades"
        bloque = (
            '<p style="color:#4b423a;font:15px/1.6 sans-serif;margin:0">'
            "Ninguna protectora ha publicado nada nuevo desde el último aviso.</p>"
        )

    caidas = [k for k, v in (data.get("salud") or {}).items() if not v.get("ok")]
    aviso = (
        f'<p style="color:#b98b2f;font:13px sans-serif;margin-top:20px">'
        f'⚠ Anoche fallaron estas fuentes: {", ".join(caidas)}.</p>'
    ) if caidas else ""

    cta = (
        f'<p style="margin:26px 0 0"><a href="{SITE}" style="background:#c4562f;color:#fff;padding:13px 24px;'
        f'border-radius:999px;text-decoration:none;font:600 15px sans-serif;display:inline-block">'
        f'Abrir el buscador</a></p>'
    ) if SITE else ""

    return f"""<!doctype html><html><body style="margin:0;background:#fbf8f4;padding:24px">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:24px;padding:30px;border:1px solid #e8e0d5">
  <p style="margin:0;color:#c4562f;font:600 11px/1 sans-serif;letter-spacing:.14em;text-transform:uppercase">
    Perrita Arias Brotóns · {hoy}
  </p>
  <h1 style="margin:12px 0 6px;font:400 30px/1.1 Georgia,serif;color:#1c1815">{titulo}</h1>
  <p style="margin:0 0 18px;color:#8b8076;font:14px sans-serif">
    {data['vivas']} fichas en seguimiento · {data['alicante']} en Alicante · {data['cachorras']} cachorras
  </p>
  {bloque}
  {aviso}{cta}
  <p style="margin:26px 0 0;color:#b3a89c;font:12px sans-serif;border-top:1px solid #e8e0d5;padding-top:14px">
    Barrido de las {(data.get('generated_at') or '')[:16].replace('T', ' ')} UTC.
    Este resumen sale todos los días a las 07:00.
  </p>
</div></body></html>"""


def build_text(data: dict) -> str:
    n = len(data["nuevas"])
    if not n:
        return (
            "Perrita Arias Brotóns\n\n"
            "Hoy no hay novedades: ninguna protectora ha publicado nada nuevo.\n\n"
            f"{data['vivas']} fichas siguen en seguimiento.\n{SITE}"
        )
    partes = [f"Perrita Arias Brotóns — {n} novedad{'es' if n != 1 else ''} de hoy"]
    for d in data["nuevas"]:
        partes.append(f"★{d['score']} {d['name']}{' ✔' if d.get('encaja') else ''} · {_meta(d)}\n{_link(d)}")
    partes.append(SITE)
    return "\n\n".join(partes)


# --------------------------------------------------------------------------- cli

def diagnostico_correo() -> list[str]:
    """Dice qué secretos hay y cuáles faltan, sin revelar ningún valor.

    Los registros de Actions de un repositorio público los ve cualquiera, así
    que aquí solo se informa de si cada secreto está definido; nunca de su
    contenido. Sin esto, un correo mal configurado se queda en una línea
    discreta dentro de un paso en verde y no hay manera de saber qué pasa.
    """
    obligatorios = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO")
    faltan = [k for k in obligatorios if not os.environ.get(k)]

    print("Configuración del correo:")
    for clave in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO"):
        valor = os.environ.get(clave)
        if not valor:
            estado = "AUSENTE" if clave in obligatorios else "sin definir (opcional)"
        elif clave == "MAIL_TO":
            n = len(recipients())
            estado = f"definido · {n} destinatario{'s' if n != 1 else ''}"
        elif clave in ("SMTP_HOST", "SMTP_PORT"):
            estado = f"definido · {valor}"
        else:
            estado = f"definido · {len(valor)} caracteres"
        print(f"  {clave:10} {estado}")

    if faltan:
        print(f"::warning title=El correo no está configurado::"
              f"Faltan estos secretos en Settings → Secrets and variables → Actions: "
              f"{', '.join(faltan)}. Sin ellos el resumen no se envía.")
    return faltan


def main() -> int:
    ap = argparse.ArgumentParser(description="Resumen matinal por correo")
    ap.add_argument("--preview", action="store_true", help="escribe el HTML y no envía nada")
    ap.add_argument("--out", default="digest-preview.html")
    args = ap.parse_args()

    data = collect()
    html = build_html(data)
    n = len(data["nuevas"])
    print(f"{n} novedades desde {data['since'][:16]} · {data['vivas']} fichas vivas")

    if args.preview:
        Path(args.out).write_text(html, encoding="utf-8")
        print("escrito", args.out)
        return 0

    if diagnostico_correo():
        # Falla a propósito: un resumen que no se envía tiene que verse en rojo,
        # no esconderse en una línea dentro de un paso en verde.
        print("::error title=Resumen no enviado::"
              "El correo no está configurado; revisa los secretos que se listan arriba.")
        return 1

    asunto = (
        f"🐾 {n} novedad{'es' if n != 1 else ''} de hoy · Perrita Arias Brotóns"
        if n else "🐾 Sin novedades hoy · Perrita Arias Brotóns"
    )
    ok = send_mail(asunto, build_text(data), html)

    if ok:
        meta = store.load_meta()
        meta["last_digest_sent"] = data["at"]
        store._write_json(store.META_JSON, meta)
        print("marca de envío guardada en meta.json")
        return 0

    print("::error title=El correo ha fallado::"
          "Los secretos están puestos pero el envío no ha salido; el motivo exacto "
          "aparece en la línea '· correo FALLÓ' de arriba.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
