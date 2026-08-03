"""Avisos de las novedades del barrido nocturno: correo y WhatsApp.

Todo es opcional y se activa solo con los secretos que existan en el
repositorio. Sin secretos, el aviso vive únicamente en la web (badge de
"Novedades"), que no necesita configuración.

Secretos que se leen del entorno:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM, MAIL_TO
    CALLMEBOT_PHONE, CALLMEBOT_APIKEY     (WhatsApp 1 a 1, https://www.callmebot.com)
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID      (grupo de Telegram)
    SITE_URL                              (para enlazar la ficha en la web)

Sobre los grupos: ninguna API oficial de WhatsApp —ni la Cloud API de Meta ni
Twilio— permite publicar en un grupo; solo admiten conversaciones uno a uno.
Por eso el canal de grupo es Telegram, y WhatsApp se queda para el aviso
individual.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import urllib.parse
from email.message import EmailMessage
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DIGEST = ROOT / "data" / "last_digest.json"
SITE = os.environ.get("SITE_URL", "").rstrip("/")


# --------------------------------------------------------------------------- texto

SIZE_LABEL = {
    "mini": "Mini", "pequeno": "Pequeña", "mediano": "Mediana",
    "grande": "Grande", "gigante": "Gigante",
}
SEX_LABEL = {"hembra": "Hembra", "macho": "Macho"}


def _age_label(months: int | None) -> str:
    if months is None:
        return "Edad sin confirmar"
    if months < 1:
        return "Recién nacida"
    if months < 24:
        return f"{months} {'mes' if months == 1 else 'meses'}"
    years, rest = divmod(months, 12)
    return f"{years} años" + (f" y {rest} m" if rest else "")


def _meta(d: dict) -> str:
    """Los tres datos que de verdad deciden: edad, talla y dónde está."""
    return " · ".join(
        x for x in (
            _age_label(d.get("age_months")),
            SIZE_LABEL.get(d.get("size") or ""),
            d.get("province"),
        ) if x
    )


def _line(d: dict) -> str:
    return f"★{d['score']}  {d['name']} · {_meta(d)}"


def _link(d: dict) -> str:
    return f"{SITE}/#{urllib.parse.quote(d['id'])}" if SITE else d.get("url", "")


def build_text(digest: dict) -> str:
    items = digest["notifiable"]
    head = f"{len(items)} novedad{'es' if len(items) != 1 else ''} para la Perrita Arias Brotóns"
    body = "\n".join(f"{_line(d)}\n{_link(d)}" for d in items[:12])
    tail = f"\n\n(+{len(items) - 12} más)" if len(items) > 12 else ""
    return f"{head}\n\n{body}{tail}"


def build_html(digest: dict) -> str:
    items = digest["notifiable"]
    rows = []
    for d in items[:20]:
        photo = d.get("photo") or ""
        img = (
            f'<img src="{photo}" width="86" height="86" alt="" '
            f'style="border-radius:14px;object-fit:cover;display:block">'
            if photo else '<div style="width:86px;height:86px;border-radius:14px;background:#f0e9df"></div>'
        )
        meta = " · ".join(
            x for x in (SEX_LABEL.get(d.get("sex") or "", "Sexo sin confirmar"), _meta(d)) if x
        )
        rows.append(f"""
<tr>
  <td style="padding:12px 0;vertical-align:top;width:98px">{img}</td>
  <td style="padding:12px 0;vertical-align:top;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1c1815">
    <a href="{_link(d)}" style="color:#c4562f;text-decoration:none;font-size:18px;font-weight:600">{d['name']}</a>
    <span style="background:#fbeae2;color:#c4562f;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700;margin-left:6px">{d['score']}</span>
    <div style="color:#8b8076;font-size:13px;margin-top:2px">{meta}</div>
    <div style="color:#4b423a;font-size:13px;margin-top:2px">{d.get('shelter') or ''}</div>
  </td>
</tr>""")

    more = f'<p style="color:#8b8076;font:13px sans-serif">Y {len(items) - 20} más en la web.</p>' if len(items) > 20 else ""
    cta = f'<p><a href="{SITE}" style="background:#c4562f;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font:600 15px sans-serif;display:inline-block">Abrir el buscador</a></p>' if SITE else ""

    return f"""<!doctype html><html><body style="margin:0;background:#fbf8f4;padding:24px">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:24px;padding:28px;border:1px solid #e8e0d5">
  <p style="margin:0;color:#c4562f;font:600 11px/1 sans-serif;letter-spacing:.14em;text-transform:uppercase">Perrita Arias Brotóns</p>
  <h1 style="margin:10px 0 4px;font:400 28px/1.1 Georgia,serif;color:#1c1815">
    {len(items)} novedad{'es' if len(items) != 1 else ''} esta noche
  </h1>
  <p style="margin:0 0 8px;color:#8b8076;font:14px sans-serif">
    De {digest['total']} fichas en seguimiento. Ordenadas por encaje con lo que buscáis.
  </p>
  <table style="width:100%;border-collapse:collapse">{''.join(rows)}</table>
  {more}{cta}
</div></body></html>"""


# --------------------------------------------------------------------------- envíos

def send_email(digest: dict) -> bool:
    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("MAIL_TO")
    if not host or not to:
        print("· correo: sin configurar (falta SMTP_HOST o MAIL_TO)")
        return False

    msg = EmailMessage()
    n = len(digest["notifiable"])
    msg["Subject"] = f"🐾 {n} perrita{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''} que encajan"
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER") or to
    msg["To"] = to
    msg.set_content(build_text(digest))
    msg.add_alternative(build_html(digest), subtype="html")

    port = int(os.environ.get("SMTP_PORT", "587"))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
                _login(s)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                _login(s)
                s.send_message(msg)
        print(f"· correo enviado a {to}")
        return True
    except Exception as exc:
        print(f"· correo FALLÓ: {exc}", file=sys.stderr)
        return False


def _login(s: smtplib.SMTP) -> None:
    user, pwd = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    if user and pwd:
        s.login(user, pwd)


def send_whatsapp(digest: dict) -> bool:
    """CallMeBot: gratuito, sin servidor y suficiente para un aviso diario."""
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        print("· whatsapp: sin configurar (falta CALLMEBOT_PHONE o CALLMEBOT_APIKEY)")
        return False

    items = digest["notifiable"][:6]
    text = "🐾 *Perrita Arias Brotóns*\n" + "\n".join(f"{_line(d)}\n{_link(d)}" for d in items)
    if len(digest["notifiable"]) > 6:
        text += f"\n\n+{len(digest['notifiable']) - 6} más"

    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": text, "apikey": apikey},
            timeout=30,
        )
        ok = r.status_code == 200
        print(f"· whatsapp: {'enviado' if ok else 'error ' + str(r.status_code)}")
        return ok
    except Exception as exc:
        print(f"· whatsapp FALLÓ: {exc}", file=sys.stderr)
        return False


def send_telegram(digest: dict) -> bool:
    """Telegram sí admite grupos: basta con meter el bot en el grupo familiar."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("· telegram: sin configurar (falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID)")
        return False

    items = digest["notifiable"]
    lines = [f"<b>🐾 {len(items)} novedad{'es' if len(items) != 1 else ''} esta noche</b>", ""]
    for d in items[:10]:
        lines.append(f'<b>{d["score"]}</b> · <a href="{_link(d)}">{d["name"]}</a> — {_meta(d)}')
        if d.get("shelter"):
            lines.append(f'<i>{d["shelter"]}</i>')
        lines.append("")
    if len(items) > 10:
        lines.append(f"…y {len(items) - 10} más")
    if SITE:
        lines.append(f'<a href="{SITE}">Abrir el buscador</a>')

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": "\n".join(lines)[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        ok = r.ok and r.json().get("ok")
        print(f"· telegram: {'enviado al grupo' if ok else 'error ' + r.text[:120]}")
        return bool(ok)
    except Exception as exc:
        print(f"· telegram FALLÓ: {exc}", file=sys.stderr)
        return False


def main() -> int:
    if not DIGEST.exists():
        print("no hay resumen del barrido; nada que notificar")
        return 0
    digest = json.loads(DIGEST.read_text(encoding="utf-8"))
    items = digest.get("notifiable", [])
    if not items:
        print("sin novedades relevantes esta noche")
        return 0

    print(f"{len(items)} novedades notificables")
    sent = [send_email(digest), send_telegram(digest), send_whatsapp(digest)]
    if not any(sent):
        print("ningún canal configurado; el aviso queda solo en la web")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
