# Perrita Arias Brotóns

Buscador de perritas en adopción para la familia Arias Brotóns: una hembra joven,
de tamaño pequeño o mediano, preferiblemente recogible en la provincia de
Alicante y, si no, en la mitad este de España.

Todo funciona sobre GitHub y nada más: la web es estática (GitHub Pages), la base
de datos son ficheros versionados en el propio repositorio y el barrido nocturno
es un GitHub Action. No hay servidor que mantener ni base de datos que pagar.

---

## Qué hay montado

| Pieza | Dónde | Qué hace |
|---|---|---|
| Buscador | `index.html` | Filtros, orden por afinidad, ficha, favoritas. Mobile-first. |
| Comparativa | `comparar.html` | Hasta cuatro candidatas cara a cara, empezando por las favoritas. |
| Base de datos | `datos.html` | Cuadro de mando y tabla completa, ordenable y filtrable. |
| Alta de fichas | `admin.html` | Formulario manual y extracción automática desde un enlace. |
| Fichero de datos | `data/dogs.json` | Una ficha por perro, con histórico en el log de git. |
| Export a Sheets | `data/exports/dogs.csv` | CSV plano listo para `IMPORTDATA`. |
| Motor de barrido | `scraper/` | Adaptadores por fuente + normalización + afinidad. |
| Barrido nocturno | `.github/workflows/nightly.yml` | 00:00 hora de Madrid, todos los días. |
| Resumen matinal | `.github/workflows/digest.yml` | 07:00 hora de Madrid, por correo. |
| Avisos | `scraper/notify.py` | Correo, Telegram y WhatsApp, además del badge en la web. |

---

## Puesta en marcha

```bash
git init && git add . && git commit -m "Perrita Arias Brotóns"
gh repo create perrita-arias-brotons --public --source=. --push
```

> GitHub Pages en repositorios **privados** requiere plan de pago. Con cuenta
> gratuita el repositorio tiene que ser público para que la web se publique.
> Aquí no hay nada sensible: los secretos viven en la configuración del
> repositorio, nunca en el código.

Después, en el repositorio:

1. **Settings → Pages → Source: GitHub Actions.** El workflow `pages.yml` publica
   el sitio en cada push.
2. **Settings → Actions → General → Workflow permissions: Read and write.**
   El barrido nocturno necesita poder commitear la base de datos.
3. **Settings → Variables → New repository variable:** `SITE_URL` con la URL
   pública (por ejemplo `https://usuario.github.io/perrita-arias-brotons`). Sirve
   para que los avisos enlacen a la ficha dentro de la web.

### Repasar la base sin volver a barrer

Cuando se corrige un normalizador, las fichas ya guardadas conservan el dato
viejo hasta que su fuente vuelve a barrerse. `repair` las repasa todas en local
—descarta lo que no es un animal, limpia nombres, corrige estados y quita
imágenes genéricas— en segundos y sin molestar a las webs de las protectoras:

```bash
python -m scraper.repair --dry-run
python -m scraper.repair
```

### Ejecutar el barrido en local

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r scraper/requirements.txt
python -m scraper.run --list          # ver las fuentes
python -m scraper.run --no-browser    # barrido completo sin Playwright
python -m scraper.run --source miwuki --limit 5 --dry-run
```

Para las webs hechas con JavaScript (Wix y similares) hace falta el navegador:

```bash
python -m playwright install chromium
python -m scraper.run                 # ya incluye las fuentes con browser
```

---

## Los avisos

Hay dos momentos, deliberadamente separados:

| Cuándo | Qué | Por dónde |
|---|---|---|
| **00:00** | Barre las ocho fuentes y guarda las novedades | Telegram y WhatsApp (aviso instantáneo) |
| **07:00** | Lee lo que guardó el barrido y manda el resumen | Correo |

Los cron de GitHub se retrasan con frecuencia —se han visto casi dos horas—, así
que ninguno de los dos exige la hora exacta: aceptan una ventana de varias horas
y comprueban en `data/meta.json` que el trabajo no se haya hecho ya hoy. Ni se
saltan la cita ni la repiten.

Separarlos evita el correo a medianoche, evita duplicar el mensaje y hace que un
fallo del scraper no deje sin resumen: el de las 07:00 solo lee la base de datos.

El resumen matinal **sale todos los días**, haya novedades o no. Cuando no las
hay, recuerda las que mejor encajan en ese momento y avisa si alguna fuente
falló por la noche. Lleva su propia marca (`last_digest_sent` en `data/meta.json`),
así que no repite fichas ni se salta ninguna aunque un día falle el envío o se
añada algo a mano por la tarde.

El aviso dentro de la web funciona sin configurar nada: cada ficha guarda cuándo
se vio por primera vez y el buscador marca como **Novedades** todo lo aparecido
desde la última visita.

Correo, Telegram y WhatsApp se activan añadiendo secretos en
**Settings → Secrets and variables → Actions**:

| Secreto | Para qué |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Servidor de salida del correo. |
| `MAIL_FROM`, `MAIL_TO` | Remitente y destinatarios. `MAIL_TO` admite varias direcciones separadas por coma. |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | Grupo de Telegram. |
| `CALLMEBOT_PHONE`, `CALLMEBOT_APIKEY` | WhatsApp individual vía [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/). |

Con Gmail hay que usar una **contraseña de aplicación**, no la del correo:
`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`.

### Avisar a un grupo

**WhatsApp no permite publicar en grupos desde ninguna API oficial.** Ni la
Cloud API de Meta ni Twilio lo contemplan: las dos están pensadas para
conversaciones uno a uno. Lo que circula por ahí para hacerlo son librerías que
secuestran una sesión de WhatsApp Web; incumplen las condiciones de uso, se
caen cada pocas semanas y pueden acabar con el número bloqueado. No merece la
pena para esto.

Así que el canal de grupo es **Telegram**, que sí lo admite de forma nativa:

1. Habla con [@BotFather](https://t.me/BotFather) y manda `/newbot`. Te da el
   token → secreto `TELEGRAM_TOKEN`.
2. Crea el grupo familiar y añade el bot como miembro.
3. Escribe cualquier cosa en el grupo y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates`. El `chat.id` que aparece
   (empieza por `-100`) es el secreto `TELEGRAM_CHAT_ID`.

Y **WhatsApp** se queda para el aviso personal: manda una vez
`I allow callmebot to send me messages` al +34 644 51 95 23 y te devuelve la
API key. Ese mensaje se puede reenviar al grupo con un toque.

Los avisos llevan **todas las altas del día, sin recortar**, ordenadas por
encaje y con un distintivo en las que cumplen lo que buscáis (hembra, hasta 12
meses, talla pequeña o mediana y en Alicante o provincias vecinas; o cualquiera
que pase de 62 puntos). Si un día no hay ninguna, el mensaje lo dice y nada más.

Telegram parte el aviso en varios mensajes cuando hace falta: su API corta a
4096 caracteres y el corte se hace entre fichas, nunca por la mitad de una.
WhatsApp es la excepción —viaja por URL y no admite mensajes largos—, así que
ahí van las seis primeras y un «+N más en el correo».

---

## Llevarlo a Google Sheets

El barrido regenera `data/exports/dogs.csv` en cada ejecución. En una hoja nueva:

```
=IMPORTDATA("https://raw.githubusercontent.com/USUARIO/REPO/main/data/exports/dogs.csv")
```

La hoja se refresca sola y arrastra los cambios de cada noche. Si el repositorio
es privado, la alternativa es descargar el CSV desde el pie de la web.

---

## Cómo se calcula el encaje

`config/criteria.json` define qué busca la familia y cuánto pesa cada cosa:

| Criterio | Peso | Puntuación máxima cuando… |
|---|---:|---|
| Sexo | 26 | es hembra |
| Edad | 26 | tiene 6 meses o menos (hasta 18 puntúa alto) |
| Tamaño | 18 | es mini, pequeña o mediana |
| Zona | 18 | está en Alicante (72 % en provincias vecinas, 42 % en la mitad este) |
| Raza | 6 | es de raza o mezcla identificada |
| Niñas | 6 | la ficha dice que es buena con niños |

Encima se aplican correcciones: las razas potencialmente peligrosas bajan al 25 %
—hay dos niñas en casa—, las adoptadas al 15 %, las reservadas al 60 %, y las
urgentes suben un 5 %. Cambiar los pesos del JSON recalcula todo el ranking en el
siguiente barrido, sin tocar código.

La web muestra el desglose en cada ficha, en «Por qué encaja».

---

## Las fuentes

Verificadas y funcionando sin navegador:

| Fuente | Tipo | Cobertura | Cómo se lee |
|---|---|---|---|
| **Miwuki Pet Shelter** | Agregador | Alicante, Valencia, Murcia, Albacete, Castellón | Búsqueda avanzada con sesión + paginación AJAX + ficha estructurada. Es la más rentable: agrupa decenas de protectoras pequeñas de Alicante. |
| **Kerubi** | Agregador | Ídem por provincias | Listado por provincia y ficha con raza/sexo/nacimiento/tamaño. |
| **Las Reinas del Biberón** | Protectora | Alicante | API de WooCommerce. Especialistas en cachorros. |
| **SPAP Villena** | Protectora | Alicante | API de WooCommerce con atributos (sexo, nacimiento, peso). |
| **APADAC Callosa de Segura** | Protectora | Alicante | Ficha con lista de definición muy limpia. |
| **Protectora de Ibi** | Protectora | Alicante | Fichas `/ficha-N`. |
| **ASOKA el Grande** | Protectora | Alicante | Fichas `/ficha-N`. |
| **ANAA** | Protectora | Madrid | Fichas `/animales/N`. |

Preparadas pero dependientes de navegador (`playwright install chromium`):

- **APAC El Campello** — la web es Wix y no devuelve nada sin renderizar.
- **Alicante Protectora (SPA Alicante)** — desactivada en `config/sources.json`:
  hoy publica sus casos solo en Instagram y Facebook, no en la web. El bloque
  está listo para activarlo si abren un listado.

### Sobre las redes sociales

Facebook e Instagram bloquean el acceso automatizado sin sesión y cambian el
marcado con frecuencia; cualquier scraper contra ellas se rompe en semanas y va
contra sus condiciones de uso. La vía que sí es estable y está montada: cuando
veas una publicación interesante, copia el enlace y pégalo en `admin.html` →
**Desde un enlace**. El extractor genérico lo convierte en ficha y lo mete en la
base de datos. `scraper/sources/browser.py` deja el motor de navegador listo por
si en algún momento interesa automatizar alguna cuenta concreta.

### Añadir una protectora nueva

Si la web es HTML normal, no hace falta escribir código: basta un bloque en
`config/sources.json`.

```json
{
  "slug": "mi-protectora",
  "label": "Protectora de Ejemplo",
  "home": "https://ejemplo.org",
  "province": "Alicante",
  "listings": ["https://ejemplo.org/adopta"],
  "detail_pattern": "/adopta/[a-z0-9-]+/?$",
  "exclude_pattern": "gatos|adoptados",
  "browser": false,
  "max_details": 80,
  "enabled": true
}
```

El extractor genérico (`scraper/sources/generic.py`) se encarga del resto:
JSON-LD, OpenGraph, listas de definición, tablas y, si no hay nada de eso,
expresiones sobre el texto. Si una web necesita lógica propia, se añade un
adaptador en `scraper/sources/` y se registra con `@register`.

---

## Añadir fichas a mano

`admin.html` no necesita configurar nada: se abre y funciona.

- **Desde un enlace** — pega la URL del anuncio. El navegador no puede leer otro
  dominio por la política CORS, así que la lectura pasa por un lector público
  (solo se le manda la URL del anuncio, que ya es pública). Rellena lo que
  encuentra y tú revisas antes de guardar.
- **A mano** — formulario en blanco con el encaje calculándose en vivo.

Al guardar, la ficha queda en el `localStorage` de ese navegador y **aparece al
instante** en el buscador, en la base de datos y en el CSV descargable, mezclada
con las del barrido y puntuada con los mismos criterios.

Vive en ese navegador, no en el repositorio: es lo que permite que funcione sin
tokens ni servidor. Desde el propio panel puedes exportarlas en JSON o en CSV
para guardarlas o pasarlas a otro dispositivo. El barrido nocturno nunca las
toca.

---

## Cómo se comporta la base de datos

- **Retira lo que ya no existe, con red de seguridad.** Una ficha que
  desaparece de su web se marca la primera noche y se borra la segunda: hacen
  falta dos ausencias seguidas. Si reaparece por el camino, se rescata. Y si una
  fuente se cae y «pierde» más del 40 % de sus fichas de golpe, se cancela la
  retirada y se anota el motivo: un tropiezo de una web no vacía la base.
- **Diff legible.** El JSON se escribe ordenado y con sangría fija, así que cada
  commit nocturno enseña exactamente qué cambió.
- **Duplicados marcados, no eliminados.** La misma perrita publicada en Miwuki y
  en Kerubi se detecta por nombre + sexo + edad + provincia; la copia se marca
  con el flag `duplicada` y se enlaza a la principal.
- **Salud por fuente.** `data/meta.json` guarda cuántas fichas y qué errores dio
  cada fuente en cada barrido: si una protectora cambia su web, se nota enseguida.

### Campos de una ficha

```
id, source, source_label, url, entry
name, sex, sex_inferred, birth_date, age_months, age_estimated, age_band
size, size_inferred, weight_kg, breed, breed_type, ppp
province, location, shelter, shelter_url, shelter_kind, contact
photo, photos[], description, traits{}, health{}
status, urgent, first_seen, last_seen, updated_at, gone_since, content_hash
score, score_breakdown{}, flags[]
```

---

## Limitaciones conocidas

- **Datos tan buenos como los publica cada protectora.** Muchas fichas no
  declaran sexo, edad o tamaño. Cuando el dato se deduce, la ficha lo dice:
  `sex_inferred`, `age_estimated`, `size_inferred`, y en la web sale como
  «sin confirmar» o con un `~`.
- El tamaño se estima a partir del peso o de la raza cuando falta.
- La geolocalización llega a provincia, no a municipio exacto.
- Las descripciones a veces contradicen los datos estructurados (una ficha puede
  decir «1 año» y tener fecha de nacimiento de hace cinco). Se prioriza siempre
  el dato estructurado.

## Siguientes fases

La base de datos y las herramientas de análisis y comparación quedan para más
adelante, como acordamos. El esquema ya guarda todo lo necesario (`score_breakdown`,
`traits`, `health`, histórico de `first_seen`/`last_seen`) para construirlas encima
sin migrar nada.
