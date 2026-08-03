/* =============================================================================
   Comparativa: se elige primero entre las favoritas y, si hace falta, entre
   todas. Hasta cuatro a la vez, que es lo que cabe legible en un móvil.
   ========================================================================== */

(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const MAX = 4;
  const PAGINA = 18;
  const state = { all: [], modo: 'fav', elegidas: [], mostradas: PAGINA };

  init();

  async function init() {
    try {
      const { dogs } = await PAB.load();
      state.all = dogs;
      const favs = dogs.filter((d) => PAB.isFav(d.id));
      $('#nFav').textContent = favs.length;
      // si aún no hay favoritas, no tiene sentido abrir en esa pestaña
      if (!favs.length) state.modo = 'todas';
      // permite llegar desde el buscador con ?ids=a,b
      const ids = new URLSearchParams(location.search).get('ids');
      if (ids) state.elegidas = ids.split(',').filter((id) => dogs.some((d) => d.id === id)).slice(0, MAX);
      wire();
      pintarTabs();
      pintarOpciones();
      pintarTabla();
    } catch (e) {
      $('#hint').textContent = 'No se ha podido cargar la base de datos: ' + e.message;
    }
  }

  function wire() {
    $('#tabFav').addEventListener('click', () => setModo('fav'));
    $('#tabTodas').addEventListener('click', () => setModo('todas'));
    let t;
    $('#q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.mostradas = PAGINA; pintarOpciones(); }, 150); });
    $('#masOpciones').addEventListener('click', () => { state.mostradas += PAGINA; pintarOpciones(); });
    $('#limpiar').addEventListener('click', () => { state.elegidas = []; pintarOpciones(); pintarTabla(); });
    $('#descargar').addEventListener('click', () => {
      const sel = state.elegidas.map(byId);
      CSV.download(sel, 'comparativa.csv');
      toast(`CSV con ${sel.length} fichas`);
    });
  }

  const byId = (id) => state.all.find((d) => d.id === id);

  function setModo(m) {
    state.modo = m;
    state.mostradas = PAGINA;
    pintarTabs();
    pintarOpciones();
  }

  function pintarTabs() {
    $('#tabFav').setAttribute('aria-selected', String(state.modo === 'fav'));
    $('#tabTodas').setAttribute('aria-selected', String(state.modo === 'todas'));
    $('#buscador').hidden = state.modo !== 'todas';
  }

  function candidatas() {
    let v = state.modo === 'fav'
      ? state.all.filter((d) => PAB.isFav(d.id))
      : state.all.filter((d) => ['disponible', 'urgente', 'acogida'].includes(d.status));
    const q = PAB.fold($('#q').value.trim());
    if (state.modo === 'todas' && q) {
      const t = q.split(/\s+/).filter(Boolean);
      v = v.filter((d) => {
        const hay = PAB.fold([d.name, d.breed, d.shelter, d.source_label, d.province].join(' '));
        return t.every((x) => hay.includes(x));
      });
    }
    return v.sort((a, b) => b.score - a.score);
  }

  function pintarOpciones() {
    const v = candidatas();
    const cont = $('#opciones');

    if (!v.length) {
      cont.innerHTML = '';
      $('#hint').innerHTML = state.modo === 'fav'
        ? 'Todavía no hay favoritas. Márcalas con el corazón en el <a href="index.html">buscador</a>, o cambia a «Todas».'
        : 'Ninguna coincide con esa búsqueda.';
      $('#masOpciones').hidden = true;
      return;
    }

    $('#hint').textContent = `${state.elegidas.length} de ${MAX} elegidas · ${v.length} disponibles`;
    cont.innerHTML = v.slice(0, state.mostradas).map((d) => {
      const on = state.elegidas.includes(d.id);
      const bloqueada = !on && state.elegidas.length >= MAX;
      return `
      <button class="opt${on ? ' is-on' : ''}" data-id="${esc(d.id)}" aria-pressed="${on}"${bloqueada ? ' disabled' : ''}>
        <span class="opt__img">${d.photo
          ? `<img src="${esc(d.photo)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : '<span class="noimg">🐕</span>'}</span>
        <span class="opt__body">
          <strong>${esc(d.name)}</strong>
          <small>${esc(PAB.ageText(d))} · ${esc(PAB.sizeText(d))}</small>
          <small>${esc(d.province || '—')}</small>
        </span>
        <span class="opt__score">${d.score}</span>
      </button>`;
    }).join('');
    $('#masOpciones').hidden = v.length <= state.mostradas;

    $$('.opt').forEach((b) => b.addEventListener('click', () => {
      const id = b.dataset.id;
      const i = state.elegidas.indexOf(id);
      if (i >= 0) state.elegidas.splice(i, 1);
      else if (state.elegidas.length < MAX) state.elegidas.push(id);
      pintarOpciones();
      pintarTabla();
    }));
  }

  /* ------------------------------------------------------------ la tabla */

  const FILAS = [
    ['Encaje', (d) => `<span class="comp__score">${d.score}</span>`, true],
    ['Sexo', (d) => PAB.sexText(d)],
    ['Edad', (d) => PAB.ageText(d)],
    ['Tamaño', (d) => PAB.sizeText(d) + (d.size_inferred ? ' *' : '')],
    ['Peso', (d) => (d.weight_kg ? `${d.weight_kg} kg` : '—')],
    ['Raza', (d) => d.breed || '—'],
    ['Tipo', (d) => ({ raza: 'De raza', mezcla: 'Mezcla', mestizo: 'Mestiza', desconocido: '—' }[d.breed_type])],
    ['Zona', (d) => `${d.province || '—'}<br><small>${PAB.TIER_LABEL[d._tier]}</small>`],
    ['Protectora', (d) => d.shelter || d.source_label],
    ['Estado', (d) => PAB.STATUS_LABEL[d.status] || d.status],
    ['Con niños', (d) => marca(d.traits?.good_with_kids)],
    ['Con perros', (d) => marca(d.traits?.good_with_dogs)],
    ['Con gatos', (d) => marca(d.traits?.good_with_cats)],
    ['Esterilizada', (d) => marca(d.health?.sterilized)],
    ['Vacunada', (d) => marca(d.health?.vaccinated)],
    ['Con chip', (d) => marca(d.health?.chipped)],
    ['PPP', (d) => (d.ppp ? '<span class="mal">Sí</span>' : 'No')],
  ];

  const marca = (v) => (v === true ? '<span class="bien">Sí</span>'
    : v === false ? '<span class="mal">No</span>' : '<span class="muted">—</span>');

  function pintarTabla() {
    const sel = state.elegidas.map(byId).filter(Boolean);
    $('#zonaTabla').hidden = sel.length < 1;
    $('#vacio').hidden = sel.length >= 1;
    if (!sel.length) return;

    // el mejor valor de cada fila se resalta para que se vea de un vistazo
    const mejorEncaje = Math.max(...sel.map((d) => d.score));

    const cab = `<thead><tr><th class="comp__lab"></th>${sel.map((d) => `
      <th class="comp__head">
        <span class="comp__photo">${d.photo
          ? `<img src="${esc(d.photo)}" alt="${esc(d.name)}" referrerpolicy="no-referrer">`
          : '<span class="noimg">🐕</span>'}</span>
        <a href="index.html#${encodeURIComponent(d.id)}">${esc(d.name)}</a>
      </th>`).join('')}</tr></thead>`;

    const cuerpo = FILAS.map(([lab, fn, destaca]) => `
      <tr>
        <th class="comp__lab">${lab}</th>
        ${sel.map((d) => {
          const v = fn(d) ?? '—';
          const top = destaca && d.score === mejorEncaje && sel.length > 1;
          return `<td class="${top ? 'is-top' : ''}">${v}</td>`;
        }).join('')}
      </tr>`).join('');

    // desglose del encaje, criterio a criterio
    const criterios = [...new Set(sel.flatMap((d) => Object.keys(d.score_breakdown || {})))]
      .filter((k) => sel.some((d) => d.score_breakdown?.[k]?.value !== undefined));
    const desglose = criterios.map((k) => `
      <tr>
        <th class="comp__lab comp__lab--sub">${esc(k)}</th>
        ${sel.map((d) => {
          const b = d.score_breakdown?.[k];
          if (!b) return '<td class="muted">—</td>';
          return `<td>
            <span class="comp__bar"><i style="width:${Math.round(b.value * 100)}%"></i></span>
            <small>${esc(b.text)}</small>
          </td>`;
        }).join('')}
      </tr>`).join('');

    $('#comp').innerHTML = cab + `<tbody>${cuerpo}
      <tr class="comp__sep"><th class="comp__lab">Por qué encaja</th>${sel.map(() => '<td></td>').join('')}</tr>
      ${desglose}</tbody>`;
  }

  let toastT;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg; el.classList.add('is-on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('is-on'), 2200);
  }
})();
