# Contexto del proyecto — Perrita Arias Brotóns

**Este documento existe para poder retomar el proyecto desde cero**, en otro
ordenador, en otra sesión o con otro asistente, sin haber vivido la
conversación en la que se construyó. Contiene lo que no se deduce leyendo el
código: por qué las cosas están hechas así, qué se probó y no funcionó, y qué
trampas hay puestas para que no se repitan errores ya cometidos.

El `README.md` explica **cómo se usa**. Esto explica **por qué es así**.

Última actualización: 5 de agosto de 2026.

---

## 1. Qué es y para quién

Una familia de Alicante —dos adultos y dos niñas— busca perra para adoptar. La
adopción la impulsa **María**, la hija mayor, y es su regalo de Comunión.

Lo que buscan, en orden de importancia:

| Criterio | Detalle |
|---|---|
| Sexo | Hembra |
| Edad | Recién nacida o muy joven (ideal ≤ 6 meses; hasta 18 puntúa alto) |
| Tamaño | Pequeño o mediano |
| Zona | Alicante provincia; si no, provincias vecinas; en último caso, mitad este de España incluida Madrid |
| Raza | Mejor de raza o mezcla identificable, pero mestiza no se descarta |
| Convivencia | Hay dos niñas: las razas PPP se penalizan fuerte |

Todo esto vive en **`config/criteria.json`**, no en el código. Cambiar los pesos
de ese fichero recalcula el ranking entero en el siguiente barrido.

**Encargo original, literal:** una web «atractiva, moderna, minimalista, pero
también espectacular y muy cuidada, funcional, sencilla y eficiente», sobre
infraestructura tipo GitHub, con base de datos estable en el tiempo y
exportable a Sheets, pensada **móvil primero**.

---

## 2. Estado actual

Publicado y funcionando en **https://flxarias.github.io/perrita-arias-brotons/**
(repositorio `flxarias/perrita-arias-brotons`, público).

- **~723 fichas** de 8 fuentes reales.
- Web con 4 secciones: buscador, comparativa, base de datos y alta de fichas.
- Barrido automático cada noche a las 00:00 de Madrid.
- Resumen por correo cada mañana a las 07:00.
- Avisos por Telegram (grupo) y WhatsApp (individual).

### Lo que falta por hacer

1. **Los secretos SMTP no están confirmados.** El correo nunca ha llegado a
   enviarse: la primera vez el resumen se saltó por un retraso del cron. Hay
   que lanzar *Resumen matinal* a mano y leer la línea `· correo:` del log, que
   dice exactamente qué pasa (sin configurar / enviado / el error de Gmail).
2. **Fase 2 del encargo**: herramientas de análisis y comparación más
   profundas. La comparativa actual es un primer paso.
3. El aviso de novedades en la web es un contador; no hay notificaciones push.

---

## 3. Decisiones de arquitectura, y por qué

### Todo estático sobre GitHub, sin servidor

La web es HTML/CSS/JS plano servido por GitHub Pages. **Sin framework, sin paso
de compilación, sin dependencias externas en el navegador.** Los ficheros se
editan y se suben; no hay `npm install` ni build que se pueda romper.

La razón de fondo: este proyecto lo tiene que poder mantener alguien dentro de
dos años sin recordar nada. Cada dependencia es una pieza que caduca.

### La base de datos es un JSON versionado en git

`data/dogs.json` es la base de datos. No hay Postgres ni Firebase.

- Se escribe con **claves ordenadas y sangría fija**, para que cada barrido
  nocturno produzca un diff legible: el historial de git *es* el historial de la
  base de datos.
- Es exportable a Sheets sin intermediarios (`data/exports/dogs.csv` +
  `IMPORTDATA`).
- No cuesta dinero ni caduca.

Pesa 2,1 MB, pero GitHub Pages lo sirve comprimido en **~306 KB**, que es
asumible en móvil.

### Las fichas dadas de alta a mano viven en el navegador

Ésta es la decisión menos obvia y conviene entenderla antes de tocarla.

El usuario pidió explícitamente que el alta manual **funcionara sin
configuración**. Un navegador no puede escribir en un repositorio de GitHub sin
un token, y pedir un token es precisamente la configuración que se quería
evitar. Solución: las fichas propias se guardan en `localStorage` y `PAB.load()`
las funde con las publicadas al cargar la página. Aparecen al instante en el
buscador, en la base de datos y en el CSV descargable.

**Consecuencia que hay que tener presente:** viven en ese navegador, no en el
repositorio. Desde el panel se pueden exportar en JSON o CSV para pasarlas a
otro dispositivo o para incorporarlas al repo con un commit.

Hubo antes una versión con token de GitHub (`assets/js/github.js`, borrado) que
sí escribía en el repositorio. Se retiró a petición del usuario.

### Los avisos van en dos momentos separados

| Cuándo | Qué hace | Canal |
|---|---|---|
| 00:00 | Barre las 8 fuentes y guarda | Telegram + WhatsApp |
| 07:00 | Lee lo guardado y resume | Correo |

Separarlos evita el correo a medianoche, evita duplicar el mensaje y hace que
**un fallo del scraper no deje sin resumen**: el de las 07:00 solo lee la base de
datos, no toca ninguna web.

### WhatsApp no puede publicar en grupos

Se investigó a fondo porque el usuario lo pidió. **Ninguna API oficial lo
permite**: ni la Cloud API de Meta ni Twilio; las dos son solo para
conversaciones uno a uno. Lo que circula para conseguirlo son librerías que
secuestran una sesión de WhatsApp Web: incumplen las condiciones, se caen cada
pocas semanas y pueden acabar con el número bloqueado.

Por eso **el canal de grupo es Telegram**, que sí lo admite de forma nativa, y
WhatsApp se queda para el aviso individual.

### El fondo animado de la portada no es un vídeo

El usuario pidió «una especie de vídeo». Se entregó un **SVG animado por CSS**:
pesa unos kB en vez de megabytes, se ve nítido a cualquier resolución, no deja
un primer fotograma negro en móvil y se detiene con `prefers-reduced-motion`.
Las ilustraciones están dibujadas a mano en el propio `index.html`.

---

## 4. Mapa del repositorio

```
index.html          Buscador (portada)
comparar.html       Comparativa cara a cara
datos.html          Cuadro de mando + tabla completa
admin.html          Alta manual y extracción desde enlace

assets/css/app.css  Toda la hoja de estilo
assets/js/
  data.js           Capa de datos: carga, vocabulario, filtros, favoritas,
                    fichas propias. Expone el objeto global PAB.
  csv.js            Genera el CSV en el navegador. Expone CSV.
  nav.js            Inyecta la cabecera común con el menú plegable.
  app.js            Buscador
  comparar.js       Comparativa
  datos.js          Base de datos
  admin.js          Alta de fichas

config/
  criteria.json     QUÉ busca la familia y cuánto pesa cada cosa
  sources.json      Fuentes declarativas (protectoras sin adaptador propio)

data/
  dogs.json         LA BASE DE DATOS
  meta.json         Última ejecución, salud por fuente, marcas de envío
  exports/dogs.csv  Export para Sheets
  last_digest.json  Puente entre el barrido y el aviso (NO se versiona)

scraper/
  run.py            Orquestador del barrido
  digest.py         Resumen matinal por correo
  notify.py         Envío por correo, Telegram y WhatsApp
  repair.py         Repasa la base sin volver a barrer
  selftest.py       Pruebas sin red — LEER ANTES DE TOCAR NADA
  core/
    models.py       Dataclass Dog y su consolidación
    normalize.py    Sexo, edad, tamaño, raza, provincia, PPP, gatos…
    scoring.py      Cálculo del encaje 0-100
    store.py        Persistencia, fusión, retirada de bajas, CSV
    http.py         Sesión con reintentos y cortesía por dominio
  sources/
    base.py         Contrato común + registro
    miwuki.py       Agregador principal
    kerubi.py       Agregador
    woocommerce.py  Reinas del Biberón y Villena
    apadac.py       APADAC Callosa
    site.py         Fuentes declarativas desde config/sources.json
    generic.py      Extractor genérico (JSON-LD, OG, dl/table, texto)
    browser.py      Playwright, degradación elegante si no está

.github/workflows/
  nightly.yml       Barrido 00:00 Madrid
  digest.yml        Resumen 07:00 Madrid
  pages.yml         Publicación
  tests.yml         CI
```

---

## 5. Las fuentes

Verificadas una a una. Ninguna necesita navegador ahora mismo.

| Fuente | Fichas | Cómo se lee |
|---|---:|---|
| **Miwuki Pet Shelter** | ~356 | Agregador. POST a `busqueda-avanzada` con filtros que quedan en la sesión, luego `?page=N` con cabecera XHR que devuelve JSON con el HTML del siguiente bloque. Es la fuente más rentable: muchas protectoras pequeñas de Alicante solo publican aquí. |
| **Kerubi** | ~192 | Agregador con listados por provincia. |
| **ANAA** (Madrid) | ~64 | Fichas en `/animales/N`. |
| **SPAP Villena** | ~56 | API de WooCommerce. |
| **APADAC Callosa** | ~20 | `<dl>` muy limpia. |
| **Las Reinas del Biberón** | ~20 | API de WooCommerce. Especialistas en cachorros. |
| **ASOKA el Grande** | ~11 | Fichas `/ficha-N`. |
| **Protectora de Ibi** | ~4 | Fichas `/ficha-N`. |
| APAC El Campello | 0 | Activa pero hoy no lista perros, solo el procedimiento. |

### Redes sociales

Facebook e Instagram **no se scrapean**. Bloquean el acceso automatizado sin
sesión, cambian el marcado constantemente y va contra sus condiciones. La vía
que sí aguanta: copiar el enlace del post y pegarlo en `admin.html`.

### Añadir una protectora nueva

Si la web es HTML normal **no hace falta escribir código**: basta un bloque en
`config/sources.json` con `listings` y `detail_pattern`. El extractor genérico
se encarga del resto. Solo se escribe un adaptador propio si la web necesita
lógica especial.

---

## 6. Errores ya cometidos — no repetirlos

Esta sección vale más que el resto del documento. Todos estos fallos están
corregidos y **casi todos tienen un caso en `scraper/selftest.py`** que los
detecta si vuelven.

### De datos

- **Las URL contaminan el análisis de la edad.** `lasreinasdelbiberon.org`
  contiene «biberon» y el parser lo leía como «recién nacida». Ahora se limpian
  URLs, emails y teléfonos antes de buscar la edad.
- **Alternancia sin agrupar en regex.** `f"{label_re}\\s*[:]..."` con
  `label_re = "a|b|c"` se interpreta como `a` OR `b` OR `c\\s*[:]...`. Hay que
  envolver: `(?:{label_re})`. Provocaba `NoneType` en el grupo capturado.
- **Kerubi cruzaba las galerías.** Cogiendo todas las `<img>` de la página se
  colaban las del bloque «Animales similares»: una sola foto llegó a aparecer en
  **189 fichas**. Hay que acotar al carrusel propio de la ficha.
- **Asoka e Ibi ponen un cartel en `og:image`.** Un «¡Adóptame!» con logotipo y
  texto. La foto real está más abajo en la página. Por eso `banner` está en la
  lista de basura.
- **Una imagen compartida por 3+ fichas es un logotipo o un «sin foto»**, nunca
  la foto de un perro. Se detecta por repetición y se pasa a la siguiente foto.
  **Solo se cuenta la foto principal**: contar las galerías se llevaba por
  delante fotos buenas.
- **Hay dos comprobaciones distintas para las imágenes.** `is_junk_img()` vale
  para cualquier URL; `_usable_img()` exige además extensión y **solo sirve para
  elegir candidatas dentro de un HTML**. Aplicar la segunda a URLs ya validadas
  borraba 354 fotos de Miwuki, que las sirve sin extensión.
- **Las webs mezclan perros y gatos**, y publican categorías con la misma
  plantilla que las fichas («Gatos En Adopción (4)», «Dona 2787», «¡Adopta!»).
  De eso se encargan `looks_like_cat()` y `looks_like_listing()`. Ojo: hay una
  perra que se llama **Dona**, así que «dona» a secas no se descarta.
- **Muchas protectoras anuncian la adopción en el nombre** («Chelsie. ADOPTADA!!»)
  sin cambiar el estado. Se detecta al consolidar la ficha.

### De la web

- **`[hidden]` pierde contra el `display` de una clase.** Sin
  `[hidden] { display: none !important; }`, el botón «Ver más» y el contador de
  filtros se veían siempre.
- **Declarar dos veces `const n` en la misma función** dejó la web entera en
  «Cargando…»: un `SyntaxError` impide que se ejecute **todo** el fichero. Por
  eso el CI pasa `node --check` sobre `assets/js`.
- **Hotlink de Villena.** `protectoravillena.com` devuelve un cartel de «This
  image was hotlinked» si la petición trae `Referer` de otro dominio: afectaba a
  sus 56 fichas. Se resuelve con `referrerpolicy="no-referrer"` en las `<img>`.
  Comprobado sobre las 714 fotos: **es el único dominio que lo hace**.
- **La caché del navegador invalida las pruebas de imagen.** Dos `<img>` con la
  misma URL reutilizan la primera respuesta: hay que probar con perfil limpio.

### De la automatización

- **Los cron de GitHub se retrasan**, se han visto **casi dos horas**. Un
  guardia que exigiera la hora exacta se saltaba la noche entera. Los dos
  workflows aceptan ahora una ventana de varias horas y consultan `meta.json`
  para no repetirse.
- **En un disparo por cron `inputs` viene vacío.** La condición
  `inputs.browser != false` daba falso y Chromium no se instalaba nunca de
  noche. Hay que leer de `github.event.inputs`, que llega como cadena.
- **El push del bot choca** si alguien empuja mientras corre el barrido. Se
  reintenta rebasando hasta tres veces.
- **Los commits hechos con el `GITHUB_TOKEN` no disparan eventos `push`.** Sin
  el encadenado `workflow_run` en `pages.yml`, la web se quedaría con los datos
  de la víspera.
- **El runner va en inglés.** `strftime("%B")` devolvía «August». Los meses se
  escriben a mano en el código.
- **Telegram corta los mensajes a 4096 caracteres.** El aviso se trocea, y el
  corte cae entre fichas, nunca por la mitad de una.

### De método

- **Auditar en condiciones distintas a las reales da resultados falsos.** La
  primera auditoría de fotos descargaba solo 64 KB (los WebP truncados no se
  decodifican) y lanzaba 10 hilos (activando los limitadores): dio 18,5 % de
  fotos rotas cuando la cifra real era 0,8 %. Y no mandaba `Referer`, que era
  justo el caso que fallaba en el navegador. **Hay que reproducir lo que hace el
  navegador.**
- **Probar una muestra por dominio no basta.** El primer diagnóstico del hotlink
  miró una foto por servidor: ocho para 723 fichas.
- **Comprobar que un fichero se ha desplegado no es comprobar que funciona.** Se
  subió un `SyntaxError` verificando solo que el texto nuevo estaba en el
  servidor.
- **Encadenar mal el shell publica código roto.** Un `python ... <<PY` que
  falla seguido de `git add` en una línea nueva sube igualmente: hay que
  encadenar con `&&`.
- **Verificar las versiones de las actions contra la API antes de escribirlas.**
  Se iba a poner `checkout@v5` cuando la actual es `v7`.

---

## 7. Trampas del entorno de desarrollo

- **`\n` dentro de un heredoc de bash acaba convertido en salto de línea real**
  y rompe las cadenas de Python y el YAML. Para texto con escapes, usar la
  edición directa de ficheros, no `sed`/heredoc.
- **Windows escribe CRLF.** `.gitattributes` normaliza a LF (los workflows
  corren en Linux) **salvo el CSV**, que lleva CRLF a propósito (RFC 4180 y
  Excel en español).
- **Para ver la web renderizada**, Chrome en modo headless funciona:
  `chrome --headless=new --screenshot=... --window-size=W,H URL`. No emula
  viewport móvil: para eso hay que meter la página en un `<iframe>` del ancho
  deseado.
- El CSV se genera **en dos sitios** (`store.py` y `csv.js`). El selftest
  comprueba que las columnas coinciden.

---

## 8. Configuración del repositorio

| Ajuste | Estado |
|---|---|
| Pages → Source: GitHub Actions | ✅ |
| Actions → Workflow permissions: Read and write | ✅ |
| Variable `SITE_URL` | ✅ |
| Secretos `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | ✅ probado |
| Secretos SMTP | ⚠️ **sin confirmar** |
| Secretos CallMeBot (WhatsApp) | ❌ sin poner |

Destinatarios del correo, en el secreto `MAIL_TO` separados por coma:
`brotons.laura@gmail.com, felixumh@gmail.com`. **No van en el código**: el
repositorio es público y dos correos personales ahí dentro los rastrean los
robots de spam en días.

Para Gmail hace falta una **contraseña de aplicación**, no la de la cuenta.

---

## 9. Cómo retomar

```bash
git clone https://github.com/flxarias/perrita-arias-brotons
cd perrita-arias-brotons
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r scraper/requirements.txt

python -m scraper.selftest        # lo primero: debe dar 0 problemas
python -m scraper.run --list      # ver las fuentes
python -m scraper.run --source apadac --limit 3 --dry-run
python -m http.server 8099        # y abrir http://localhost:8099
```

**Antes de tocar el scraper, leer `scraper/selftest.py`.** Cada caso está ahí
porque algo se rompió una vez.

Reglas de trabajo que el usuario ha ido marcando:

1. **Verificar en las condiciones reales**, no en las cómodas.
2. **No dar por bueno lo que no se ha visto funcionar.**
3. Contar los errores propios en cuanto se detectan, sin adornos.
4. Cada cambio va con su commit descriptivo, explicando el *por qué*.
5. La web se actualiza sola al empujar a `main`; hay que comprobar que el
   despliegue sale verde.
