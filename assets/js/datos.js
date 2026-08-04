/* =============================================================================
   Base de datos: resumen arriba y tabla completa debajo.
   ========================================================================== */

(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const PAGINA = 60;
  const VIVAS = ['disponible', 'urgente', 'acogida'];

  const COLS = [
    { k: 'score',    t: 'Encaje',     num: true,  val: (d) => d.score },
    { k: 'name',     t: 'Nombre',     val: (d) => d.name },
    { k: 'sex',      t: 'Sexo',       val: (d) => PAB.sexText(d) },
    { k: 'age',      t: 'Edad',       num: true,  val: (d) => PAB.ageText(d), ord: (d) => d.age_months ?? 9e3 },
    { k: 'size',     t: 'Tamaño',     val: (d) => PAB.sizeText(d), ord: (d) => PAB.SIZE_ORDER.indexOf(d.size) },
    { k: 'breed',    t: 'Raza',       val: (d) => d.breed || '—' },
    { k: 'province', t: 'Provincia',  val: (d) => d.province || '—' },
    { k: 'shelter',  t: 'Protectora', val: (d) => d.shelter || d.source_label },
    { k: 'status',   t: 'Estado',     val: (d) => PAB.STATUS_LABEL[d.status] || d.status },
    { k: 'first',    t: 'Fecha de alta', val: (d) => PAB.fechaCorta(d.first_seen), ord: (d) => d.first_seen || '' },
  ];

  const state = { all: [], vista: [], orden: 'score', asc: false, mostradas: PAGINA, meta: null, propias: 0 };

  init();

  async function init() {
    try {
      const { dogs, meta, generatedAt, propias } = await PAB.load();
      state.all = dogs;
      state.meta = meta;
      state.propias = propias;
      $('#lede').textContent = `${dogs.length} fichas recogidas de ${new Set(dogs.map((d) => d.source)).size} fuentes.`
        + (generatedAt ? ` Último barrido: ${new Date(generatedAt).toLocaleString('es-ES', { dateStyle: 'long', timeStyle: 'short' })}.` : '');
      pintarDash();
      pintarBarras();
      pintarFuentes();
      cabecera();
      wire();
      refrescar();
    } catch (e) {
      $('#lede').textContent = 'No se ha podido cargar la base de datos: ' + e.message;
    }
  }

  /* ------------------------------------------------------------- resumen */

  function pintarDash() {
    const d = state.all;
    const vivas = d.filter((x) => VIVAS.includes(x.status));
    const encaja = vivas.filter((x) => x.sex === 'hembra' && (x.age_months ?? 999) <= 18
      && ['mini', 'pequeno', 'mediano'].includes(x.size) && ['core', 'near'].includes(x._tier) && !x.ppp);
    const medio = vivas.length ? Math.round(vivas.reduce((a, x) => a + x.score, 0) / vivas.length) : 0;

    const tarjetas = [
      ['Fichas totales', d.length, ''],
      ['En seguimiento', vivas.length, ''],
      ['Encajan de lleno', encaja.length, 'is-accent'],
      ['Hembras', vivas.filter((x) => x.sex === 'hembra').length, ''],
      ['Cachorras', vivas.filter((x) => x.sex === 'hembra' && (x.age_months ?? 999) <= 12).length, ''],
      ['En Alicante', vivas.filter((x) => x._tier === 'core').length, ''],
      ['Encaje medio', medio, ''],
      ['Fichas propias', state.propias, state.propias ? 'is-accent' : ''],
    ];
    $('#dash').innerHTML = tarjetas.map(([t, v, c]) =>
      `<div class="dash__card"><dt>${t}</dt><dd class="${c}">${v}</dd></div>`).join('');
  }

  function pintarBarras() {
    const vivas = state.all.filter((x) => VIVAS.includes(x.status));
    const grupos = [
      ['Sexo', cuenta(vivas, (d) => PAB.sexText(d))],
      ['Tamaño', cuenta(vivas, (d) => PAB.sizeText(d))],
      ['Etapa', cuenta(vivas, (d) => (d.age_band ? PAB.BAND_LABEL[d.age_band] : 'Sin confirmar'))],
      ['Zona', cuenta(vivas, (d) => PAB.TIER_LABEL[d._tier])],
    ];
    $('#bars').innerHTML = grupos.map(([titulo, pares]) => {
      const max = Math.max(...pares.map(([, n]) => n), 1);
      return `<div class="bars__group">
        <h4>${titulo}</h4>
        ${pares.map(([k, n]) => `
          <div class="bars__row">
            <span class="bars__label">${esc(k)}</span>
            <span class="bars__track"><i style="width:${Math.round(100 * n / max)}%"></i></span>
            <span class="bars__n">${n}</span>
          </div>`).join('')}
      </div>`;
    }).join('');
  }

  const cuenta = (arr, fn) => {
    const m = new Map();
    arr.forEach((d) => { const k = fn(d); m.set(k, (m.get(k) || 0) + 1); });
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };

  function pintarFuentes() {
    const salud = state.meta?.source_health || {};
    const filas = cuenta(state.all, (d) => d.source_label || d.source).map(([nombre, n]) => {
      const dogs = state.all.filter((d) => (d.source_label || d.source) === nombre);
      const medio = Math.round(dogs.reduce((a, x) => a + x.score, 0) / dogs.length);
      const ultima = dogs.map((d) => d.last_seen).filter(Boolean).sort().pop() || '';
      const slug = dogs[0]?.source;
      const ok = salud[slug] ? (salud[slug].ok ? '' : ' ⚠') : '';
      return `<tr><td>${esc(nombre)}${ok}</td><td class="num">${n}</td><td class="num">${medio}</td><td>${ultima.slice(0, 10)}</td></tr>`;
    }).join('');
    $('#tfuentes').innerHTML = filas;
  }

  /* --------------------------------------------------------------- tabla */

  function cabecera() {
    $('#thead').innerHTML = COLS.map((c) =>
      `<th class="${c.num ? 'num' : ''}" data-k="${c.k}" tabindex="0" role="button" aria-label="Ordenar por ${c.t}">${c.t}<span class="sort-ind"></span></th>`).join('');
    $$('#thead th').forEach((th) => {
      const ordenar = () => {
        const k = th.dataset.k;
        if (state.orden === k) state.asc = !state.asc;
        else { state.orden = k; state.asc = k !== 'score'; }
        state.mostradas = PAGINA;
        refrescar();
      };
      th.addEventListener('click', ordenar);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ordenar(); } });
    });
  }

  function wire() {
    let t;
    $('#q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.mostradas = PAGINA; refrescar(); }, 150); });
    $('#fEstado').addEventListener('change', () => { state.mostradas = PAGINA; refrescar(); });
    $('#masFilas').addEventListener('click', () => { state.mostradas += PAGINA; refrescar(); });
    $('#descargar').addEventListener('click', () => {
      CSV.download(state.vista, 'perrita-arias-brotons.csv');
      toast(`CSV con ${state.vista.length} fichas`);
    });
  }

  function refrescar() {
    const q = PAB.fold($('#q').value.trim());
    const modo = $('#fEstado').value;

    let v = state.all;
    if (modo === 'vivas') v = v.filter((d) => VIVAS.includes(d.status));
    if (modo === 'propias') v = v.filter((d) => d.entry === 'manual' || d.entry === 'link');
    if (q) {
      const t = q.split(/\s+/).filter(Boolean);
      v = v.filter((d) => {
        const hay = PAB.fold([d.name, d.breed, d.shelter, d.source_label, d.province, d.status].join(' '));
        return t.every((x) => hay.includes(x));
      });
    }

    const col = COLS.find((c) => c.k === state.orden) || COLS[0];
    const key = col.ord || col.val;
    v = [...v].sort((a, b) => {
      const x = key(a), y = key(b);
      const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es');
      return state.asc ? r : -r;
    });
    state.vista = v;

    $('#tcount').textContent = `${v.length} fichas` + (v.length > state.mostradas ? ` · mostrando ${state.mostradas}` : '');
    $('#tbody').innerHTML = v.slice(0, state.mostradas).map((d) => `
      <tr${d.entry === 'manual' || d.entry === 'link' ? ' class="propia"' : ''}>
        ${COLS.map((c) => {
          const val = c.val(d);
          if (c.k === 'name') {
            return `<td><a href="index.html#${encodeURIComponent(d.id)}">${esc(val)}</a></td>`;
          }
          return `<td class="${c.num ? 'num' : ''}">${esc(val)}</td>`;
        }).join('')}
      </tr>`).join('');
    $('#masFilas').hidden = v.length <= state.mostradas;

    $$('#thead th').forEach((th) => {
      th.querySelector('.sort-ind').textContent =
        th.dataset.k === state.orden ? (state.asc ? ' ↑' : ' ↓') : '';
    });

    $('#nota').textContent = state.propias
      ? `${state.propias} ficha${state.propias === 1 ? '' : 's'} tuya${state.propias === 1 ? '' : 's'} guardada${state.propias === 1 ? '' : 's'} en este navegador, ya incluida${state.propias === 1 ? '' : 's'} aquí y en el CSV.`
      : '';
  }

  let toastT;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg; el.classList.add('is-on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('is-on'), 2200);
  }
})();
