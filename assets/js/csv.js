/* =============================================================================
   Genera el CSV desde el navegador, con las fichas propias ya incluidas.

   Las columnas y los valores son EXACTAMENTE los de scraper/core/store.py: si
   se toca uno hay que tocar el otro, y el selftest comprueba que coinciden.
   ========================================================================== */

const CSV = (() => {
  'use strict';

  const COLUMNAS = [
    'Encaje', 'Nombre', 'Sexo', 'Edad', 'Edad (meses)', 'Etapa', 'Nacimiento',
    'Tamaño', 'Peso (kg)', 'Raza', 'Tipo de raza', 'PPP',
    'Provincia', 'Zona', 'Localidad', 'Protectora', 'Tipo de protectora',
    'Estado', 'Urgente', 'Buena con niños', 'Esterilizada', 'Vacunada', 'Con chip',
    'Duplicada', 'Origen', 'Alta', 'Última revisión', 'Ficha', 'Foto', 'Descripción', 'Id',
  ];

  const SI_NO = (v) => (v === true ? 'Sí' : v === false ? 'No' : '');
  const SEXO = { hembra: 'Hembra', macho: 'Macho' };
  const ETAPA = { cachorro: 'Cachorra', joven: 'Joven', adulto: 'Adulta', senior: 'Senior' };
  const TIPO_RAZA = { raza: 'De raza', mezcla: 'Mezcla', mestizo: 'Mestiza', desconocido: '' };
  const ESTADO = {
    disponible: 'Disponible', urgente: 'Urgente', reservado: 'Reservada',
    adoptado: 'Adoptada', acogida: 'En acogida', 'no-disponible': 'Ya no aparece',
  };
  const ZONA = {
    core: 'Alicante', near: 'Provincia vecina', east: 'Mitad este',
    far: 'Fuera de zona', desconocido: '',
  };

  // sin caracteres de control, en una sola línea y sin espacios dobles
  const limpio = (t) => (t || '')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ' ')
    .replace(/\s+/g, ' ').trim();

  const numero = (v) => {
    if (v === null || v === undefined || v === '') return '';
    const f = Number(v);
    return Number.isFinite(f) ? String(Number.isInteger(f) ? f : f) : '';
  };

  function fila(d) {
    return {
      'Encaje': d.score,
      'Nombre': limpio(d.name),
      'Sexo': SEXO[d.sex] || '',
      'Edad': PAB.ageText(d) === 'Edad sin confirmar' ? '' : PAB.ageText(d),
      'Edad (meses)': d.age_months == null ? '' : d.age_months,
      'Etapa': ETAPA[d.age_band] || '',
      'Nacimiento': d.birth_date || '',
      'Tamaño': PAB.SIZE_LABEL[d.size] || '',
      'Peso (kg)': numero(d.weight_kg),
      'Raza': limpio(d.breed),
      'Tipo de raza': TIPO_RAZA[d.breed_type] || '',
      'PPP': SI_NO(Boolean(d.ppp)),
      'Provincia': d.province || '',
      'Zona': ZONA[d._tier || PAB.tierOf(d.province)] || '',
      'Localidad': limpio(d.location),
      'Protectora': limpio(d.shelter || d.source_label),
      'Tipo de protectora': limpio(d.shelter_kind),
      'Estado': ESTADO[d.status] || d.status,
      'Urgente': SI_NO(Boolean(d.urgent)),
      'Buena con niños': SI_NO(d.traits?.good_with_kids),
      'Esterilizada': SI_NO(d.health?.sterilized),
      'Vacunada': SI_NO(d.health?.vaccinated),
      'Con chip': SI_NO(d.health?.chipped),
      'Duplicada': SI_NO((d.flags || []).includes('duplicada')),
      'Origen': d.source_label || d.source,
      'Alta': (d.first_seen || '').slice(0, 10),
      'Última revisión': (d.last_seen || '').slice(0, 10),
      'Ficha': d.url || '',
      'Foto': d.photo || '',
      'Descripción': limpio(d.description),
      'Id': d.id,
    };
  }

  const escapa = (v) => {
    const s = String(v ?? '');
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };

  /** CSV completo, con BOM y CRLF para que Excel en español lo abra bien. */
  function build(dogs) {
    const filas = [...dogs].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, 'es'));
    const lineas = [COLUMNAS.join(',')];
    for (const d of filas) {
      const f = fila(d);
      lineas.push(COLUMNAS.map((c) => escapa(f[c])).join(','));
    }
    return '﻿' + lineas.join('\r\n') + '\r\n';
  }

  function download(dogs, nombre = 'perrita-arias-brotons.csv') {
    const blob = new Blob([build(dogs)], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = nombre;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return { COLUMNAS, fila, build, download };
})();
