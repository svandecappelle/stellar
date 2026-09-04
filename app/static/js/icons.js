/* ============================================================
   icons.js — pictogrammes au trait, une seule grille 24x24.
   Le trait prend var(--acc) via la CSS : aucune couleur ici.
   ============================================================ */

const P = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;

const ICONS = {
  /* --- bâtiments --- */
  power_station: P('<path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-6h6v6"/><path d="M12 4V2"/>'),
  mater_extractor: P('<path d="M3 21h18"/><path d="M6 21V12l6-4 6 4v9"/><path d="M9 21v-5h6v5"/><path d="M12 8V4"/>'),
  rafinery: P('<path d="M3 21h18"/><path d="M5 21V10l4 3V10l4 3V7l6 4v10"/><path d="M8 4h3"/>'),
  economical_center: P('<path d="M3 21h18"/><path d="M5 21V8l7-5 7 5v13"/><path d="M10 21v-6h4v6"/><path d="M9 11h6"/>'),
  factory: P('<path d="M3 21h18"/><path d="M4 21V9l5 3V9l5 3V6h6v15"/><path d="M17 10h1"/>'),
  shipyard: P('<path d="M3 20h18"/><path d="M6 20V11l6-4 6 4v9"/><path d="M10 20v-4h4v4"/><path d="M9 11h6"/>'),
  academy: P('<path d="M12 4 2 9l10 5 10-5-10-5Z"/><path d="M6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/>'),

  /* --- vaisseaux --- */
  Fighter: P('<path d="M12 3 8 13h8L12 3Z"/><path d="M8 13 3 17h18l-5-4"/><path d="M12 13v7"/>'),
  Interceptor: P('<path d="M12 2 9 11h6L12 2Z"/><path d="M9 11 4 15v3l5-2"/><path d="M15 11l5 4v3l-5-2"/><path d="M12 11v10"/>'),
  Cruiser: P('<path d="M3 12h18"/><path d="M5 12V9l6-3 8 3v3"/><path d="M6 12v4h12v-4"/><path d="M11 6V3"/>'),
  Frigate: P('<path d="M2 13h20"/><path d="M4 13V8l8-4 8 4v5"/><path d="M6 13v5h12v-5"/><path d="M12 4V2"/><path d="M9 8h6"/>'),
  MotherShip: P('<path d="M2 12h20"/><path d="M4 12V7l8-4 8 4v5"/><path d="M5 12v6h14v-6"/><path d="M9 7h6"/><path d="M12 18v3"/>'),
  OrbitalStation: P('<circle cx="12" cy="12" r="4"/><path d="M2 12h6"/><path d="M16 12h6"/><path d="M4 9v6"/><path d="M20 9v6"/>'),
  DefenseSatellite: P('<circle cx="12" cy="12" r="3"/><path d="M5 5l4 4"/><path d="M19 19l-4-4"/><path d="M3 7h4V3"/><path d="M21 17h-4v4"/>'),

  /* --- défenses --- */
  FlackCannon: P('<path d="M4 20h16"/><path d="M7 20v-4h6v4"/><path d="M10 16 18 8"/><path d="M15 5h5v5"/>'),
  MissileBattery: P('<path d="M4 20h16"/><path d="M7 20v-6h4v6"/><path d="M13 20v-6h4v6"/><path d="M9 14V8l0-4"/><path d="M15 14V8l0-4"/>'),
  LaserArtillery: P('<path d="M4 20h16"/><path d="M8 20v-5h4v5"/><path d="M10 15V6"/><path d="M7 9h6"/><path d="M17 4l3 3-3 3"/>'),
  IonArtillery: P('<path d="M4 20h16"/><path d="M8 20v-4h8v4"/><circle cx="12" cy="10" r="3"/><path d="M12 4v3"/><path d="M6 7l2 2"/><path d="M18 7l-2 2"/>'),
  Coilgun: P('<path d="M4 20h16"/><path d="M6 20v-3h5v3"/><path d="M8 17 20 7"/><path d="M11 14l2 2"/><path d="M14 11l2 2"/>'),
  Shield: P('<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/>'),
};

const FALLBACK = P('<rect x="4" y="4" width="16" height="16"/><path d="M9 12h6"/>');

export function icon(name) {
  return ICONS[name] || FALLBACK;
}

/* Dégradé de planète déterministe : même territoire, même bille. */
export function planetGradient(seed) {
  const palettes = [
    ['#E0A868', '#8A4E1E', '#3A1E08'],
    ['#9FD8E8', '#3E7E96', '#12303E'],
    ['#C9D3D8', '#6B7A82', '#242D33'],
    ['#F2E2B8', '#C08A3E', '#5A3A12'],
    ['#B8D8B0', '#4E7E52', '#1E3A22'],
    ['#D9B8E8', '#7A4E96', '#301240'],
  ];
  const p = palettes[Math.abs(seed) % palettes.length];
  const x = 28 + ((Math.abs(seed) * 7) % 12);
  const y = 24 + ((Math.abs(seed) * 11) % 12);
  return `radial-gradient(circle at ${x}% ${y}%,${p[0]},${p[1]} 56%,${p[2]})`;
}

export const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'];

export function roman(n) {
  return ROMAN[n - 1] || String(n);
}
