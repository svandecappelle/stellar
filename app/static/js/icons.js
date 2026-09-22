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

  /* --- flottes ---
     Une flotte n'est pas un vaisseau : trois fanions en formation, comme un
     chevron tactique. */
  fleet: P('<path d="M12 3 9 9h6l-3-6Z"/><path d="M6 12 4 16h4l-2-4Z"/><path d="M18 12l-2 4h4l-2-4Z"/><path d="M12 9v6"/><path d="M6 16h12"/>'),

  /* --- défenses --- */
  FlackCannon: P('<path d="M4 20h16"/><path d="M7 20v-4h6v4"/><path d="M10 16 18 8"/><path d="M15 5h5v5"/>'),
  MissileBattery: P('<path d="M4 20h16"/><path d="M7 20v-6h4v6"/><path d="M13 20v-6h4v6"/><path d="M9 14V8l0-4"/><path d="M15 14V8l0-4"/>'),
  LaserArtillery: P('<path d="M4 20h16"/><path d="M8 20v-5h4v5"/><path d="M10 15V6"/><path d="M7 9h6"/><path d="M17 4l3 3-3 3"/>'),
  IonArtillery: P('<path d="M4 20h16"/><path d="M8 20v-4h8v4"/><circle cx="12" cy="10" r="3"/><path d="M12 4v3"/><path d="M6 7l2 2"/><path d="M18 7l-2 2"/>'),
  Coilgun: P('<path d="M4 20h16"/><path d="M6 20v-3h5v3"/><path d="M8 17 20 7"/><path d="M11 14l2 2"/><path d="M14 11l2 2"/>'),
  Shield: P('<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z"/>'),

  /* --- interface ---
     Les commandes de la barre du haut. Meme grille et meme trait que le reste :
     un pictogramme d'interface qui ne ressemble pas aux autres se lit comme une
     image, pas comme un bouton. */
  galaxy: P('<ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-25 12 12)"/>'
    + '<circle cx="12" cy="12" r="2"/><circle cx="18" cy="8" r=".7"/>'
    + '<circle cx="6" cy="16" r=".7"/>'),
  worlds: P('<circle cx="7" cy="7" r="3"/><circle cx="17" cy="17" r="3"/>'
    + '<path d="M13 7h7"/><path d="M4 17h7"/>'),
  refresh: P('<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>'),
  menu: P('<circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/>'
    + '<circle cx="12" cy="19" r="1.4"/>'),
  settings: P('<circle cx="12" cy="12" r="3"/>'
    + '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>'),
  logout: P('<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4"/>'
    + '<path d="M16 8l4 4-4 4"/><path d="M20 12H10"/>'),
  research: P('<circle cx="12" cy="12" r="2.4"/>'
    + '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>'
    + '<path d="M6.5 6.5 9 9M15 15l2.5 2.5M17.5 6.5 15 9M9 15l-2.5 2.5"/>'),
  /* La vue d'empire : un tableau de bord, pas une carte. Quatre cases — ce
     qu'on vient y faire est de regarder tous ses mondes cote a cote. */
  empire: P('<rect x="3" y="4" width="7.5" height="7"/><rect x="13.5" y="4" width="7.5" height="7"/>'
    + '<rect x="3" y="14" width="7.5" height="6"/><rect x="13.5" y="14" width="7.5" height="6"/>'),
  sliders: P('<path d="M4 7h10M18 7h2"/><path d="M4 17h4M12 17h8"/>'
    + '<circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>'),
};

const FALLBACK = P('<rect x="4" y="4" width="16" height="16"/><path d="M9 12h6"/>');

export function icon(name) {
  return ICONS[name] || FALLBACK;
}

/* Les six billes de planete : clair, teinte, ombre.

   Publiees a part du degrade CSS parce qu'un SECOND lecteur en a besoin : la
   carte de la galaxie peint les mondes d'un systeme en SVG, ou un
   `radial-gradient` CSS n'a pas cours. Deux tables de couleurs auraient fini
   par diverger, et le meme monde n'aurait pas eu la meme bille selon l'ecran
   ou on le regarde. */
const PLANET_PALETTES = [
  ['#E0A868', '#8A4E1E', '#3A1E08'],
  ['#9FD8E8', '#3E7E96', '#12303E'],
  ['#C9D3D8', '#6B7A82', '#242D33'],
  ['#F2E2B8', '#C08A3E', '#5A3A12'],
  ['#B8D8B0', '#4E7E52', '#1E3A22'],
  ['#D9B8E8', '#7A4E96', '#301240'],
];

/* Où se pose la lumière sur la bille, en pourcentage de son diamètre. La même
   des deux côtés : c'est ce qui fait reconnaître un monde d'une vue à
   l'autre. */
export function planetPalette(seed) {
  const n = Math.abs(Math.round(Number(seed) || 0));
  return {
    colors: PLANET_PALETTES[n % PLANET_PALETTES.length],
    x: 28 + ((n * 7) % 12),
    y: 24 + ((n * 11) % 12),
  };
}

/* Dégradé de planète déterministe : même territoire, même bille. */
export function planetGradient(seed) {
  const { colors, x, y } = planetPalette(seed);
  return `radial-gradient(circle at ${x}% ${y}%,${colors[0]},${colors[1]} 56%,${colors[2]})`;
}

export const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'];

export function roman(n) {
  return ROMAN[n - 1] || String(n);
}
