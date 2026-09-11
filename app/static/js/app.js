/* ============================================================
   app.js — console Stellar.
   Trois vues : login, sélection de territoire, scène système.
   Aucune valeur de jeu n'est codée ici : coûts, gains et durées
   viennent tous de l'API.
   ============================================================ */

import { api, ApiError } from './api.js';
import { icon, planetGradient, roman } from './icons.js';

/* ---------- thèmes ---------- */
const THEMES = [
  { key: 'nebula', label: 'Nebula Grid' },
  { key: 'admiralty', label: 'Admiralty' },
  { key: 'drydock', label: 'Drydock' },
];
const THEME_STORAGE_KEY = 'stellar.theme';

/* ---------- ressources ----------
   `material: true` = extraite du sol, donc soumise à l'archétype de la
   planète. Les autres sont produites par un bâtiment dédié, partout. */
const RESOURCES = [
  { key: 'iron', code: 'FE', label: 'Fer', material: true },
  { key: 'carbon', code: 'CB', label: 'Carbone', material: true },
  { key: 'silicium', code: 'SI', label: 'Silicium', material: true },
  { key: 'titanium', code: 'TI', label: 'Titane', material: true },
  { key: 'cristal', code: 'CY', label: 'Cristal', material: true },
  { key: 'uranium', code: 'UR', label: 'Uranium', material: true },
  { key: 'hydrogen', code: 'HY', label: 'Hydrogène', material: true },
  { key: 'neutronium', code: 'NE', label: 'Neutronium', material: true },
  { key: 'credits', code: 'CR', label: 'Crédits' },
  { key: 'energy', code: 'EN', label: 'Énergie' },
  { key: 'food', code: 'FD', label: 'Nourriture' },
  { key: 'population', code: 'PO', label: 'Population' },
  { key: 'tritium', code: 'TR', label: 'Tritium' },
  /* Les Donnees ne pendent a aucun monde : la reserve est imperiale, remplie
     par les academies de tous les territoires et lue par l'arbre
     technologique. Elles figurent ici pour que les couts de recherche
     s'affichent comme les autres, mais elles n'ont rien a faire dans le
     bandeau d'un territoire — voir `visibleResources`. */
  { key: 'research', code: 'DAT', label: 'Données', empire: true },
];

const RESOURCE_BY_KEY = Object.fromEntries(RESOURCES.map((r) => [r.key, r]));

/* ---------- descriptions (texte d'interface, pas de règles de jeu) ---------- */
const BUILDING_DESC = {
  power_station: "Installation de production d'énergie. Alimente l'ensemble des systèmes planétaires.",
  mater_extractor:
    "Complexe minier de surface. Ce qu'il remonte dépend entièrement du sous-sol : "
    + "une géante gazeuse ne donnera jamais de titane, quel que soit son niveau.",
  rafinery: 'Raffinerie de tritium. Transforme les volatils captés en carburant de vol.',
  economical_center: 'Centre économique. Convertit l’activité du territoire en crédits.',
  factory: 'Usine planétaire. Réduit la durée de toutes les constructions du territoire.',
  shipyard: "Complexe de construction spatiale. Débloque l'assemblage des vaisseaux et des défenses.",
  academy: 'Académie de recherche. Prérequis des programmes technologiques avancés.',
  farm: "Ferme planetaire. Seule source de nourriture, et la nourriture est ce qui fait "
    + "croitre la population : reserve vide, la croissance s'arrete et la stabilite "
    + "descend. Son rendement depend de la fertilite du monde.",
  depot: "Entrepots, grues et mat d'amarrage. Une ligne de commerce en demande un "
    + "AUX DEUX BOUTS, et coule au rythme du plus faible des deux. Rien d'autre ne "
    + "deplace de ressources d'un monde a l'autre — et un monde coupe du reseau perd "
    + "de la stabilite a chaque heure.",
  gas_cracker: "Tours de craquage : elles cassent l'hydrogene en tritium. Le seul "
    + "batiment nourri par une ressource au lieu du sol, et la raison d'arrimer une "
    + "plateforme au-dessus d'une geante gazeuse — le tritium verrouille l'academie, "
    + "l'usine et le chantier naval.",
};

/* ---------- état ---------- */
const state = {
  theme: 'nebula',
  user: null,
  myTerritories: [],
  territoryId: null,
  territory: null,
  systemTerritories: [],
  events: [],
  /* Les flottes du systeme, avec leur position Unity et ce qu'elles portent.
     Il n'y a plus de vaisseaux a lire sur un territoire : ce qui sort du
     chantier part en orbite, dans une flotte. */
  fleets: [],
  defenses: [],
  catalog: { ships: [], defenses: [] },
  tab: 'buildings',
  /* Galaxie de travail. Un territoire appartient a un systeme, qui appartient
     a une galaxie : tout ce qu'on liste en decoule. */
  galaxy: null,
  galaxies: [],
  /* Reglages de la galaxie courante et droit d'y toucher, tels que le serveur
     les rend. Relus a chaque changement de galaxie. */
  moderation: null,
  /* Carte de la galaxie. La topologie — systemes et liaisons — ne bouge pas en
     cours de partie et n'est relue qu'au changement de galaxie ; les flottes,
     elles, se relisent et s'avancent sur l'horloge locale. */
  /* L'arbre technologique. `tree` est le catalogue — couts, durees, prerequis,
     effets — qui ne depend d'aucun joueur et se lit une fois ; `state` est
     l'etat du joueur dedans, relu a chaque geste. Aucune regle n'est recopiee
     ici : le client dessine ce que le serveur decrit. */
  research: {
    open: false,
    loading: false,
    /* La fenêtre du canevas : `{x, y, w, h}` en unités de dessin, c'est-à-dire
       le `viewBox` du SVG. Se déplacer la fait glisser, zoomer la rétrécit ;
       aucun point du tracé ne bouge. Même mécanique que `state.map.view`. */
    view: null,
    viewBranch: null,
    dragged: false,
    /* Les noeuds que le catalogue annonce et dont le joueur n'a aucun etat :
       une base en retard d'une migration. Vide en temps normal. */
    unknown: new Set(),
    warned: false,
    tree: null,
    tiers: {},
    branches: [],
    nodes: new Map(),
    cards: new Map(),
    state: null,
    branch: null,
    selected: null,
    readAt: 0,
    tick: 0,
  },
  map: {
    galaxy: null,
    systems: [],
    lanes: [],
    fleets: [],
    byId: new Map(),
    rank: new Map(),
    projection: null,
    /* Le cadrage courant, en unites de vue : c'est lui le `viewBox` du SVG.
       Deplacer et zoomer se ramenent a le bouger et le retailler, ce qui ne
       touche a aucun point du trace. */
    view: null,
    dragged: false,
    readAt: 0,
    selectedSystem: null,
    selectedFleet: null,
    tick: 0,
  },
};

let tickTimer = null;
let pollTimer = null;
let researchTimer = null;
let reloading = false;
/* Événements dont on a déjà constaté la fin : le serveur les archive au
   prochain /update, mais tant qu'ils reviennent on ne relance qu'une fois. */
let settledEvents = new Set();

/* ============================================================
   utilitaires
   ============================================================ */

const $ = (sel) => document.querySelector(sel);

/* Branche un gestionnaire, et ne fait rien si l'element manque.
   ---
   `$('#x').addEventListener(...)` leve dès que `#x` n'est pas là, et cette
   exception remonte jusqu'à `boot()` : un seul bouton absent du balisage
   emportait TOUTE la console, écran de connexion compris. Le balisage et le
   script sont deux fichiers servis séparément, et rien ne garantit qu'un
   visiteur ait les deux dans la même version — un cache tenace suffit. Le
   défaut doit rester local à l'écran concerné. */
function on(selector, event, handler, options) {
  const element = $(selector);
  if (element) element.addEventListener(event, handler, options);
  return element;
}

/* ---------- la vue vit dans le chemin ----------

     /                              le menu, tant qu'aucune galaxie n'est choisie
     /galaxy/<nom>                  la carte, qui est la vue d'accueil
     /galaxy/<nom>/territory/<id>   un monde

   Dans le chemin et non dans la requete : c'est une adresse de page, pas un
   filtre. Elle se met en favori, se partage et se recharge, et le bouton retour
   du navigateur retrouve la vue precedente au lieu de sortir du site.

   `/api` est a l'API : rien ne se chevauche. Le serveur rend la meme page pour
   tous ces chemins (voir `app/web/ui.py`), c'est ici qu'on decide de ce qu'elle
   montre. */
function readRoute() {
  let parts = [];
  try {
    parts = window.location.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  } catch (e) {
    /* Chemin mal encode : on retombe sur l'accueil plutot que d'echouer. */
    parts = [];
  }

  if (parts[0] !== 'galaxy' || !parts[1]) {
    /* Ancienne forme `?galaxy=` : les liens deja poses continuent de marcher,
       et la premiere navigation les reecrit dans la nouvelle. */
    let legacy = null;
    try {
      legacy = new URLSearchParams(window.location.search).get('galaxy');
    } catch (e) {
      legacy = null;
    }
    return { galaxy: legacy || null, territoryId: null };
  }

  const id = parts[2] === 'territory' && parts[3] ? Number(parts[3]) : null;
  return {
    galaxy: parts[1],
    territoryId: Number.isFinite(id) && id > 0 ? id : null,
    research: parts[2] === 'research',
  };
}

function routePath(galaxy, territoryId, research = false) {
  if (!galaxy) return '/';
  const base = `/galaxy/${encodeURIComponent(galaxy)}`;
  if (territoryId) return `${base}/territory/${territoryId}`;
  /* La recherche est imperiale et traverse les galaxies, mais l'adresse en
     porte une : c'est celle ou l'on travaille, et celle qui decide des mondes
     affiches partout ailleurs. */
  return research ? `${base}/research` : base;
}

/* Ecrit l'adresse de la vue courante.

   `replace` quand la vue n'est pas un pas de navigation — une correction de
   l'adresse, ou le premier affichage : empiler une entree la ferait apparaitre
   dans l'historique comme un endroit ou revenir. */
function syncUrl({ replace = false } = {}) {
  const path = routePath(state.galaxy, state.territoryId, state.research.open);
  try {
    if (path === window.location.pathname && !window.location.search) return;
    const entry = {
      galaxy: state.galaxy,
      territoryId: state.territoryId,
      research: state.research.open,
    };
    if (replace) window.history.replaceState(entry, '', path);
    else window.history.pushState(entry, '', path);
  } catch (e) {
    /* pas d'historique disponible : la vue reste juste, l'URL ne suit pas */
  }
}

function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

/* "ResourceType.mater" -> "mater", "PositionalEventType.ship" -> "ship" */
function bare(value) {
  const s = String(value || '');
  const dot = s.lastIndexOf('.');
  return dot === -1 ? s : s.slice(dot + 1);
}

/* Les dates du serveur sont des datetime.utcnow() sans fuseau :
   sans le Z, le navigateur les lirait en heure locale. */
function parseUtc(iso) {
  if (!iso) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function humanize(name) {
  return String(name || '')
    .replace(/_/g, ' ')
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtNumber(n) {
  const v = Number(n) || 0;
  const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10;
  return rounded.toLocaleString('fr-FR');
}

function fmtDelta(n) {
  const v = Number(n) || 0;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${fmtNumber(Math.abs(v))}`;
}

function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m ${String(sec).padStart(2, '0')}s`;
  return `${sec}s`;
}

/* Les coûts/gains arrivent indexés par "ResourceType.x" : on remet à plat. */
function normalizeResourceMap(map) {
  const out = {};
  Object.entries(map || {}).forEach(([k, v]) => {
    const n = Number(v) || 0;
    if (n) out[bare(k)] = n;
  });
  return out;
}

function toast(message, kind = 'info', title = null) {
  const host = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast${kind === 'err' ? ' err' : ''}`;
  el.innerHTML = `${title ? `<span class="ov">${esc(title)}</span>` : ''}${esc(message)}`;
  host.appendChild(el);
  setTimeout(() => el.remove(), kind === 'err' ? 7000 : 4000);
}

/* ============================================================
   thème
   ============================================================ */

function applyTheme(key) {
  state.theme = key;
  document.body.className = `theme-${key}`;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, key);
  } catch (e) {
    /* navigation privée : le thème reste celui de la session */
  }
  document.querySelectorAll('.theme-pick').forEach(renderThemePicker);
}

function renderThemePicker(host) {
  host.innerHTML = THEMES.map(
    (t) =>
      `<button class="tab${t.key === state.theme ? ' on' : ''}" data-theme="${t.key}" title="Direction ${esc(t.label)}">${esc(t.label)}</button>`
  ).join('');
}

function initTheme() {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_STORAGE_KEY);
  } catch (e) {
    stored = null;
  }
  applyTheme(THEMES.some((t) => t.key === stored) ? stored : 'nebula');

  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-theme]');
    if (btn) applyTheme(btn.dataset.theme);
  });
}

/* ============================================================
   galaxies
   ============================================================ */

async function loadGalaxies() {
  const known = await api.galaxies().catch(() => []);
  state.galaxies = Array.isArray(known) ? known.map((g) => g.name).filter(Boolean) : [];

  // Priorite : ce que dit l'adresse, puis la galaxie deja choisie, puis la
  // premiere connue.
  const route = readRoute();
  const wanted = route.galaxy || state.galaxy;
  state.galaxy =
    (wanted && state.galaxies.includes(wanted) && wanted) || state.galaxies[0] || wanted || null;

  /* Le reste de l'adresse est repris ici, et c'est necessaire : la
     normalisation ci-dessous ecrit `routePath(state...)`, qui ne connait que
     l'etat. Sans ces deux lignes, elle reduisait toute adresse a sa galaxie
     avant meme la connexion — un lien vers un monde precis, ou vers la
     recherche, etait donc efface au chargement, et `applyRoute` relisait une
     adresse deja tronquee. La vue s'ouvrait sur la carte, quel que soit le lien
     suivi. */
  state.territoryId = route.territoryId;
  state.research.open = route.research;

  fillGalaxySelect($('#login-galaxy'));
  fillGalaxySelect($('#pick-galaxy'));
  syncUrl({ replace: true });
}

function fillGalaxySelect(select) {
  if (!select) return;
  if (!state.galaxies.length) {
    select.innerHTML = '<option value="">Aucune galaxie</option>';
    return;
  }
  select.innerHTML = state.galaxies
    .map(
      (name) =>
        `<option value="${esc(name)}"${name === state.galaxy ? ' selected' : ''}>${esc(name)}</option>`
    )
    .join('');
}

/* Changer de galaxie relit les possessions : ce sont deux jeux de territoires
   sans rapport, et rien de la galaxie precedente ne doit rester a l'ecran. */
async function switchGalaxy(name) {
  if (!name || name === state.galaxy) return;
  state.galaxy = name;
  state.territoryId = null;
  state.territory = null;
  /* Changer de galaxie est bien un pas de navigation : on doit pouvoir revenir
     a la precedente. */
  syncUrl();
  fillGalaxySelect($('#login-galaxy'));
  fillGalaxySelect($('#pick-galaxy'));
  if (state.user) await enterGame();
}

/* ============================================================
   navigation entre vues
   ============================================================ */

function showView(name) {
  ['login', 'pick', 'command', 'moderation', 'galaxy', 'research', 'admin'].forEach(
    (v) => {
      $(`#view-${v}`).classList.toggle('hidden', v !== name);
    }
  );
  if (name !== 'command') stopTimers();
  if (name !== 'galaxy') stopMapTimers();
  if (name !== 'research') leaveResearch();
}

/* ============================================================
   administration du serveur

   Trois choses, dans l'ordre où l'on s'en inquiète : l'état du schéma, les
   réglages de la machine, et le journal de ce que les joueurs ont demandé.

   L'entrée du menu reste cachée tant que le compte ne porte pas le rôle
   `admin`. Ce n'est qu'une politesse : la barrière est sur les routes, et
   cacher un bouton n'a jamais empêché personne d'appeler une URL. C'est
   d'ailleurs pour cela que la tentative est journalisée.
   ============================================================ */

const ADMIN = {
  tab: 'state',
  settings: null,
  audit: null,
  page: 1,
  filters: {},
};

function isAdmin() {
  const roles = (state.user && state.user.roles) || [];
  return roles.some((r) => r.type === 'admin');
}

/* Relu à chaque entrée : un rôle peut être retiré entre deux sessions, et
   `api.login` ne renvoie pas les rôles — seul `/api/auth/me` les porte. */
function applyAdminAccess() {
  const allowed = isAdmin();
  document
    .querySelectorAll('[data-act="admin"]')
    .forEach((el) => el.classList.toggle('hidden', !allowed));
}

async function openAdmin() {
  if (!isAdmin()) return;

  stopTimers();
  stopMapTimers();
  showView('admin');
  showAdminTab(ADMIN.tab);
}

function showAdminTab(name) {
  ADMIN.tab = name;

  document.querySelectorAll('[data-admin-tab]').forEach((tab) => {
    tab.classList.toggle('admin-tab--on', tab.dataset.adminTab === name);
  });
  document.querySelectorAll('[data-admin-pane]').forEach((pane) => {
    pane.classList.toggle('hidden', pane.dataset.adminPane !== name);
  });

  if (name === 'state') loadSchema();
  if (name === 'settings') loadServerSettings();
  if (name === 'audit') loadAudit();
}

/* ---- état du schéma ---- */

async function loadSchema() {
  const box = $('#admin-schema');
  box.innerHTML = '<p class="empty">Lecture…</p>';

  let body;
  try {
    body = await api.schema();
  } catch (e) {
    box.innerHTML = `<p class="empty">${esc(
      e instanceof ApiError ? e.message : 'Lecture impossible'
    )}</p>`;
    return;
  }

  /* Le ton suit l'état : à jour en vert, en retard en rouge. Un schéma en
     retard n'est pas une information, c'est une action à mener — et il ne se
     voit autrement qu'au premier accès à une colonne absente. */
  const bad = !body.up_to_date;
  const pending = body.pending || [];

  box.innerHTML = `
    <div class="admin-state ${bad ? 'admin-state--bad' : 'admin-state--ok'}">
      <span class="admin-state__badge">${esc(body.state)}</span>
      <span class="admin-state__text">${esc(body.message)}</span>
    </div>
    <div class="admin-grid">
      <div><span class="ov">Révision de la base</span>
        <span class="admin-rev">${esc(body.revision || '—')}</span></div>
      <div><span class="ov">Attendue par le code</span>
        <span class="admin-rev">${esc(body.head || '—')}</span></div>
      <div><span class="ov">Migrations en attente</span>
        <span class="admin-rev">${pending.length}</span></div>
    </div>
    ${
      pending.length
        ? `<div class="rule"></div>
           <span class="ov">À jouer, de la plus ancienne</span>
           <ol class="admin-pending">${pending
             .map(
               (p) =>
                 `<li><code>${esc(p.revision)}</code> ${esc(
                   (p.description || '').split('\n')[0]
                 )}</li>`
             )
             .join('')}</ol>`
        : ''
    }
    ${
      bad
        ? `<div class="rule"></div>
           <p class="mod-intro">La migration ne se lance pas depuis cette page :
             elle déplace des données, et la déclencher depuis plusieurs
             instances à la fois est le genre de décision qui revient à
             l'opérateur. Sur le serveur :</p>
           <pre class="admin-cmd">${esc(body.command)}</pre>`
        : ''
    }`;
}

/* ---- réglages du serveur ---- */

async function loadServerSettings() {
  const box = $('#admin-settings');
  box.innerHTML = '<p class="empty">Lecture…</p>';

  try {
    ADMIN.settings = await api.serverSettings();
  } catch (e) {
    box.innerHTML = `<p class="empty">${esc(
      e instanceof ApiError ? e.message : 'Lecture impossible'
    )}</p>`;
    return;
  }

  renderServerSettings();
}

function renderServerSettings(values = null) {
  const data = ADMIN.settings;
  if (!data) return;

  const settings = values || data.settings || {};

  /* Le formulaire est construit à partir de ce que le serveur décrit, bornes
     comprises : c'est lui qui applique le réglage, c'est à lui de dire ce qu'il
     fait. Redire ici les bornes les ferait diverger au premier changement. */
  $('#admin-settings').innerHTML = (data.parameters || [])
    .map((p) => {
      const value = settings[p.key];
      const changed = Object.prototype.hasOwnProperty.call(data.overrides || {}, p.key);
      return `<div class="mod-field">
        <div class="mod-field__head">
          <label for="set-${esc(p.key)}">${esc(p.label)}</label>
          <span class="mod-field__state">${changed ? 'modifié' : 'par défaut'}</span>
        </div>
        <p class="mod-field__help">${esc(p.description)}</p>
        <div class="mod-field__row">
          ${settingInput(p, value)}
          ${p.unit ? `<span class="mod-field__bounds">${esc(p.unit)}</span>` : ''}
          <span class="mod-field__bounds">${esc(boundsOf(p))}</span>
        </div>
        <p class="mod-field__help">Appliqué par <code>${esc(p.applied_by)}</code></p>
      </div>`;
    })
    .join('');
}

function settingInput(p, value) {
  const id = `set-${esc(p.key)}`;
  if (p.kind === 'bool') {
    return `<input type="checkbox" id="${id}" data-setting="${esc(p.key)}"
              data-kind="bool" ${value ? 'checked' : ''}>`;
  }
  if (p.kind === 'int') {
    return `<input type="number" id="${id}" data-setting="${esc(p.key)}"
              data-kind="int" value="${esc(String(value ?? p.default))}"
              min="${esc(String(p.min))}" max="${esc(String(p.max))}" step="1">`;
  }
  return `<input type="text" id="${id}" data-setting="${esc(p.key)}"
            data-kind="text" value="${esc(String(value ?? ''))}"
            maxlength="${esc(String(p.max_length || 500))}">`;
}

function boundsOf(p) {
  if (p.kind === 'int') return `${p.min} – ${p.max} · défaut ${p.default}`;
  if (p.kind === 'bool') return `défaut ${p.default ? 'oui' : 'non'}`;
  return `${p.max_length} caractères au plus`;
}

function readServerSettings() {
  const wanted = {};
  document.querySelectorAll('[data-setting]').forEach((input) => {
    const key = input.dataset.setting;
    if (input.dataset.kind === 'bool') wanted[key] = input.checked;
    else if (input.dataset.kind === 'int') wanted[key] = Number(input.value);
    else wanted[key] = input.value;
  });
  return wanted;
}

async function saveServerSettings() {
  const err = $('#admin-settings-error');
  const btn = $('#admin-settings-save');
  err.classList.add('hidden');
  btn.disabled = true;

  try {
    const answer = await api.saveServerSettings(readServerSettings());
    /* Relu depuis la réponse et non depuis le formulaire : le serveur efface
       les valeurs égales au défaut, et l'état « modifié » de chaque ligne doit
       suivre. */
    ADMIN.settings = await api.serverSettings();
    renderServerSettings(answer.settings);
    toast('Réglages enregistrés.', 'ok', 'Serveur');
  } catch (e) {
    err.textContent = e instanceof ApiError ? e.message : 'Enregistrement impossible';
    err.classList.remove('hidden');
  } finally {
    btn.disabled = false;
  }
}

function resetServerSettings() {
  const data = ADMIN.settings;
  if (!data) return;
  /* Remet les défauts DANS LE FORMULAIRE, sans enregistrer : le geste reste
     réversible tant qu'on n'a pas cliqué sur Enregistrer. */
  renderServerSettings(data.defaults);
}

/* ---- journal d'audit ---- */

async function loadAudit() {
  const box = $('#admin-audit');
  box.innerHTML = '<p class="empty">Lecture…</p>';

  try {
    ADMIN.audit = await api.audit({ ...ADMIN.filters, page: ADMIN.page, size: 50 });
  } catch (e) {
    box.innerHTML = `<p class="empty">${esc(
      e instanceof ApiError ? e.message : 'Lecture impossible'
    )}</p>`;
    return;
  }

  fillAuditActions(ADMIN.audit.actions || []);
  renderAudit();

  /* La liste des comptes n'est lue qu'une fois : elle sert à compléter le champ
     « joueur », pas à être tenue à jour à la seconde. */
  if (!ADMIN.players) {
    ADMIN.players = await api.players().catch(() => []);
    $('#audit-players').innerHTML = ADMIN.players
      .map((p) => `<option value="${esc(p.username)}">`)
      .join('');
  }
}

function fillAuditActions(actions) {
  const select = $('#audit-action');
  if (select.dataset.filled) return;
  select.innerHTML =
    '<option value="">tous</option>' +
    actions.map((a) => `<option value="${esc(a)}">${esc(a)}</option>`).join('');
  select.dataset.filled = '1';
}

function renderAudit() {
  const data = ADMIN.audit;
  if (!data) return;

  if (!data.entries.length) {
    $('#admin-audit').innerHTML = '<p class="empty">Aucune ligne pour ce filtre.</p>';
  } else {
    $('#admin-audit').innerHTML = `<table class="audit">
      <thead><tr>
        <th>Quand</th><th>Joueur</th><th>Geste</th>
        <th>Issue</th><th>Route</th><th>Détails</th>
      </tr></thead>
      <tbody>${data.entries.map(auditRow).join('')}</tbody>
    </table>`;
  }

  $('#audit-count').textContent = `${data.total} ligne(s) · page ${data.page}/${data.pages} · conservées ${data.retention_days} jours`;
  $('#audit-prev').disabled = data.page <= 1;
  $('#audit-next').disabled = data.page >= data.pages;
}

function auditRow(entry) {
  const when = parseUtc(entry.created_at);
  const refused = entry.outcome === 'refused';
  return `<tr class="${refused ? 'audit--bad' : ''}">
    <td class="audit__when">${when ? esc(when.toLocaleString('fr-FR')) : '—'}</td>
    <td>${esc(entry.username || '—')}<span class="audit__ip">${esc(
      entry.address || ''
    )}</span></td>
    <td><code>${esc(entry.action)}</code></td>
    <td>${refused ? `<span class="audit__code">${esc(String(entry.status || ''))}</span>` : 'ok'}</td>
    <td class="audit__route">${esc(entry.route || '—')}</td>
    <td class="audit__details">${esc(summarise(entry.details))}</td>
  </tr>`;
}

/* Une ligne de tableau ne peut pas porter un objet entier. On rend les clés
   utiles à plat, et l'on s'arrête : la charge complète est en base pour qui
   veut creuser, la vue sert à repérer ce qui sort de l'ordinaire. */
function summarise(details) {
  if (!details) return '';
  const flat = details.payload ? { ...details, ...details.payload } : details;
  delete flat.payload;

  return Object.entries(flat)
    .map(([key, value]) => {
      if (value && typeof value === 'object') {
        return `${key}=${JSON.stringify(value).slice(0, 60)}`;
      }
      return `${key}=${value}`;
    })
    .join(' · ')
    .slice(0, 180);
}

function readAuditFilters() {
  ADMIN.filters = {
    user: $('#audit-user').value.trim(),
    action: $('#audit-action').value,
    outcome: $('#audit-outcome').value,
    status: $('#audit-status').value,
  };
  ADMIN.page = 1;
}

async function purgeAudit() {
  const days = window.prompt(
    'Effacer les lignes plus vieilles que combien de jours ?',
    String((ADMIN.audit && ADMIN.audit.retention_days) || 30)
  );
  if (!days) return;

  try {
    const done = await api.purgeAudit(Number(days));
    toast(`${done.removed} ligne(s) effacée(s).`, 'ok', 'Journal');
    await loadAudit();
  } catch (e) {
    handleApiError(e, 'Journal');
  }
}

function initAdmin() {
  $('#admin-back').addEventListener('click', () => applyRoute({ push: false }));

  document.querySelectorAll('[data-admin-tab]').forEach((tab) => {
    tab.addEventListener('click', () => showAdminTab(tab.dataset.adminTab));
  });

  $('#admin-settings-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    saveServerSettings();
  });
  $('#admin-settings-reset').addEventListener('click', resetServerSettings);

  $('#audit-apply').addEventListener('click', () => {
    readAuditFilters();
    loadAudit();
  });
  $('#audit-clear').addEventListener('click', () => {
    $('#audit-user').value = '';
    $('#audit-action').value = '';
    $('#audit-outcome').value = '';
    $('#audit-status').value = '';
    readAuditFilters();
    loadAudit();
  });
  $('#audit-prev').addEventListener('click', () => {
    ADMIN.page = Math.max(1, ADMIN.page - 1);
    loadAudit();
  });
  $('#audit-next').addEventListener('click', () => {
    ADMIN.page += 1;
    loadAudit();
  });
  $('#audit-purge').addEventListener('click', purgeAudit);
}

/* ============================================================
   modération de galaxie

   Les réglages décident des durées et des rendements : tout joueur peut les
   lire, seul un modérateur de la galaxie peut les changer. La vue n'affiche
   donc pas un formulaire au hasard — elle affiche celui que le serveur décrit,
   bornes comprises, et se met en lecture seule quand `can_edit` est faux.
   ============================================================ */

/* Relu à chaque changement de galaxie : le droit de modérer se porte sur une
   galaxie, pas sur un compte. */
async function refreshModeration() {
  state.moderation = null;
  if (!state.galaxy) {
    applyModerationAccess();
    return;
  }

  try {
    state.moderation = await api.galaxySettings(state.galaxy);
  } catch (e) {
    /* Réglages illisibles : la partie reste jouable, le bouton reste caché. */
    state.moderation = null;
  }
  applyModerationAccess();
}

function applyModerationAccess() {
  const allowed = !!(state.moderation && state.moderation.can_edit);
  document
    .querySelectorAll('[data-act="moderation"]')
    .forEach((el) => el.classList.toggle('hidden', !allowed));
  const pick = $('#pick-moderation');
  if (pick) pick.classList.toggle('hidden', !allowed);
}

async function openModeration() {
  if (!state.galaxy) return;

  stopTimers();
  showView('moderation');
  $('#mod-error').classList.add('hidden');
  $('#mod-fields').innerHTML = '<p class="empty">Chargement…</p>';

  try {
    state.moderation = await api.galaxySettings(state.galaxy);
  } catch (e) {
    handleApiError(e, 'Réglages indisponibles');
    return;
  }

  renderModeration();
  applyModerationAccess();
}

function renderModeration(values = null) {
  const data = state.moderation;
  if (!data) return;

  const settings = values || data.settings || {};
  const editable = !!data.can_edit;

  $('#mod-galaxy').textContent = data.galaxy_name || state.galaxy || '—';

  const moderators = Array.isArray(data.moderators) ? data.moderators : [];
  $('#mod-moderators').innerHTML = moderators.length
    ? `<span class="dep"><span class="ov">Modérateurs</span><span>${esc(
        moderators.join(', ')
      )}</span></span>`
    : `<span class="dep"><span class="ov">Modérateurs</span><span>aucun</span></span>`;

  const updated = parseUtc(data.updated_at);
  $('#mod-updated').textContent = updated
    ? `Modifié le ${updated.toLocaleString()}`
    : 'Jamais modifié';

  $('#mod-fields').innerHTML = (data.parameters || [])
    .map((parameter) => {
      const value = settings[parameter.key];
      const isDefault = Number(value) === Number(parameter.default);
      return `<div class="mod-field">
        <div class="mod-field__head">
          <label for="mod-${esc(parameter.key)}">${esc(parameter.label)}</label>
          <span class="kb">${esc(parameter.key)}</span>
        </div>
        <p class="mod-field__help">${esc(parameter.description)}</p>
        <div class="mod-field__row">
          <input id="mod-${esc(parameter.key)}" name="${esc(parameter.key)}" type="number"
                 value="${esc(value)}" step="${esc(parameter.step)}"
                 min="${esc(parameter.min)}" max="${esc(parameter.max)}"
                 ${editable ? '' : 'disabled'}>
          <span class="mod-field__bounds">${esc(parameter.min)} – ${esc(parameter.max)}</span>
          <span class="mod-field__state">${
            isDefault ? 'valeur par défaut' : `défaut ${esc(parameter.default)}`
          }</span>
        </div>
      </div>`;
    })
    .join('');

  $('#mod-save').classList.toggle('hidden', !editable);
  $('#mod-reset').classList.toggle('hidden', !editable);
}

/* Le formulaire entier part à chaque enregistrement : le serveur ignore ce qui
   n'a pas bougé et efface ce qui revient au défaut. */
function readModerationForm() {
  const data = state.moderation;
  const values = {};
  (data.parameters || []).forEach((parameter) => {
    const field = $(`#mod-${parameter.key}`);
    if (field) values[parameter.key] = Number(field.value);
  });
  return values;
}

async function saveModeration(values) {
  const err = $('#mod-error');
  const btn = $('#mod-save');
  err.classList.add('hidden');
  btn.disabled = true;
  btn.textContent = 'Enregistrement…';

  try {
    const saved = await api.saveGalaxySettings(state.galaxy, values);
    state.moderation = Object.assign({}, state.moderation, saved);
    renderModeration();
    toast(`Réglages de ${state.galaxy} enregistrés.`, 'info', 'Modération');
  } catch (e) {
    err.textContent = e instanceof ApiError ? e.message : 'Enregistrement impossible';
    err.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Enregistrer';
  }
}

function leaveModeration() {
  if (state.territoryId) {
    showView('command');
    startTimers();
    reloadTerritory(true);
    return;
  }
  renderPicker();
  showView('pick');
}

function initModeration() {
  $('#mod-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    saveModeration(readModerationForm());
  });

  $('#mod-reset').addEventListener('click', () => {
    const data = state.moderation;
    if (!data) return;
    /* Remise à zéro explicite : on envoie les défauts, le serveur efface les
       réglages plutôt que d'enregistrer des valeurs qui ne changent rien. */
    renderModeration(data.defaults || {});
    saveModeration(Object.assign({}, data.defaults || {}));
  });

  $('#mod-back').addEventListener('click', leaveModeration);
  /* L'entree de la barre du haut passe par `data-act` ; celle de l'ecran de
     choix reste un bouton nomme, cet ecran n'ayant pas de menu. */
  $('#pick-moderation').addEventListener('click', openModeration);
}

/* ============================================================
   login
   ============================================================ */

/* Connexion ou inscription. Un seul formulaire, deux modes : les deux gestes ne
   different que par le courriel et la confirmation.

   La verification faite ici ne remplace pas celle du serveur — elle evite
   l'aller-retour qui dirait la meme chose une demi-seconde plus tard. Les
   bornes sont donc celles du serveur, et quand elles divergeront c'est lui qui
   aura raison : son refus s'affiche tel qu'il l'a ecrit. */
const LOGIN_MIN_USER = 3;
const LOGIN_MAX_USER = 32;
const LOGIN_MIN_PASS = 8;

let registering = false;

function setLoginMode(creating) {
  registering = creating;

  $('#login-overline').textContent = creating ? 'Nouveau compte' : 'Accès opérateur';
  $('#login-submit').textContent = creating ? 'Créer le compte' : 'Se connecter';
  $('#login-switch').textContent = creating ? "J'ai déjà un compte" : 'Créer un compte';

  $('#login-email-field').classList.toggle('hidden', !creating);
  $('#login-confirm-field').classList.toggle('hidden', !creating);
  $('#login-hint').classList.toggle('hidden', !creating);
  $('#login-error').classList.add('hidden');

  /* Désactivés, et pas seulement masqués. Un champ caché reste candidat à la
     validation du navigateur : un courriel mal saisi puis abandonné en
     repassant en connexion bloquerait la soumission — sans message visible,
     puisque le champ qu'il faudrait montrer n'est plus à l'écran. */
  $('#login-email').disabled = !creating;
  $('#login-confirm').disabled = !creating;

  /* Le navigateur propose le mot de passe enregistre sur `current-password`, et
     en propose un nouveau sur `new-password`. Laisser l'attribut inchange lui
     ferait remplir un formulaire d'inscription avec un ancien mot de passe. */
  $('#login-pass').setAttribute(
    'autocomplete',
    creating ? 'new-password' : 'current-password'
  );
}

/* Ce qui ne va pas dans la saisie, null si elle peut partir. */
function checkLogin(username, password) {
  if (username.length < LOGIN_MIN_USER || username.length > LOGIN_MAX_USER) {
    return `Le nom doit faire entre ${LOGIN_MIN_USER} et ${LOGIN_MAX_USER} caractères.`;
  }
  if (!password) return 'Saisissez votre mot de passe.';

  /* Un compte créé avant que la règle n'existe peut avoir un mot de passe plus
     court : le mesurer à la connexion refuserait son propriétaire chez lui. La
     longueur ne se vérifie qu'à l'inscription. */
  if (!registering) return null;

  if (password.length < LOGIN_MIN_PASS) {
    return `Le mot de passe doit faire au moins ${LOGIN_MIN_PASS} caractères.`;
  }
  if (password !== $('#login-confirm').value) {
    return 'Les deux mots de passe ne correspondent pas.';
  }
  const email = $('#login-email').value.trim();
  if (email.length < 5 || !email.includes('@')) {
    return 'Une adresse de courriel valide est requise.';
  }
  return null;
}

/* Ce que le serveur annonce avant toute connexion : un message d'accueil, et
   si les inscriptions sont ouvertes.

   Cacher le bouton « Créer un compte » n'est qu'une politesse — elle évite de
   remplir un formulaire qui sera refusé. La barrière est dans `POST /api/users`,
   et elle tient qu'on ait vu ce bouton ou non. */
async function loadServerNotice() {
  let notice;
  try {
    notice = await api.server();
  } catch (e) {
    /* Un serveur qui ne répond pas à cette route reste parfaitement jouable :
       elle n'apporte qu'un confort. */
    return;
  }

  const box = $('#login-announcement');
  box.textContent = notice.announcement || '';
  box.classList.toggle('hidden', !notice.announcement);

  if (notice.registration_open === false) {
    $('#login-switch').classList.add('hidden');
    if (registering) setLoginMode(false);
  }
}

function initLogin() {
  setLoginMode(false);

  $('#login-switch').addEventListener('click', () => setLoginMode(!registering));

  $('#login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('#login-submit');
    const err = $('#login-error');
    const username = $('#login-user').value.trim();
    const password = $('#login-pass').value;

    const wrong = checkLogin(username, password);
    if (wrong) {
      err.textContent = wrong;
      err.classList.remove('hidden');
      return;
    }

    const creating = registering;
    err.classList.add('hidden');
    btn.disabled = true;
    btn.textContent = creating ? 'Création…' : 'Connexion…';
    try {
      const chosen = $('#login-galaxy').value;
      if (chosen) {
        state.galaxy = chosen;
      }

      /* L'inscription ouvre la session dans la foulée : son résultat EST le
         compte connecté, il n'y a pas de connexion à enchaîner. */
      state.user = creating
        ? await api.register(username, $('#login-email').value.trim(), password)
        : await api.login(username, password);

      $('#login-pass').value = '';
      $('#login-confirm').value = '';
      if (creating) setLoginMode(false);
      await enterGame();
    } catch (e) {
      err.textContent = e instanceof ApiError ? e.message : 'Connexion impossible';
      err.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      /* Le mode courant, et non celui du départ : une inscription réussie
         ramène au mode connexion, et le libellé doit suivre. */
      btn.textContent = registering ? 'Créer le compte' : 'Se connecter';
    }
  });
}

async function logout() {
  stopTimers();
  try {
    await api.logout();
  } catch (e) {
    /* la session locale est de toute façon abandonnée */
  }
  state.user = null;
  state.territory = null;
  state.territoryId = null;
  syncUrl({ replace: true });
  showView('login');
}

/* ============================================================
   sélection de territoire
   ============================================================ */

function renderPicker() {
  const list = $('#pick-list');
  $('#pick-sub').textContent = state.myTerritories.length
    ? 'Choisissez le territoire à administrer.'
    : `Aucun territoire ne vous est attribué dans ${state.galaxy || 'cette galaxie'}.`;

  if (!state.myTerritories.length) {
    list.innerHTML = `<p class="empty">Aucun territoire attribué à ${esc(
      (state.user && state.user.username) || 'ce compte'
    )} dans ${esc(state.galaxy || 'cette galaxie')}.<br>
    Réclamez une planète depuis le client de jeu, ou choisissez une autre galaxie ci-contre.</p>
    <button class="menu-btn menu-btn--dgr" data-action="logout">Déconnexion <span class="kb">ESC</span></button>`;
    return;
  }

  list.innerHTML =
    state.myTerritories
      .map(
        (t, i) => `<button class="menu-btn" data-territory="${t.id}">
        ${esc(territoryLabel(t))}
        <span class="kb">${esc(
          [galaxyOf(t), (t.system && t.system.name) || `SYS ${t.system ? t.system.id : '—'}`]
            .filter(Boolean)
            .join(' · ')
        )}</span>
      </button>`
      )
      .join('') +
    `<button class="menu-btn menu-btn--dgr" data-action="logout">Déconnexion <span class="kb">ESC</span></button>`;
}

/* Un territoire appartient a un systeme, qui appartient a une galaxie. Le
   serveur remonte `galaxy_name` a la racine ; `system.galaxy` reste le repli
   pour les charges utiles plus anciennes. */
function galaxyOf(t) {
  if (!t) return null;
  return t.galaxy_name || (t.system && t.system.galaxy) || null;
}

function territoryLabel(t) {
  if (t.name) return t.name;
  if (t.characteristics && t.characteristics.name) return t.characteristics.name;
  const sys = (t.system && t.system.name) || `Système ${t.system ? t.system.id : '?'}`;
  return `${sys} · orbite ${roman(t.position || 1)}`;
}

function territorySubtitle(t) {
  if (t.archetype_label) return t.archetype_label;
  const scheme = t.characteristics && t.characteristics.planeteScheme;
  return scheme ? humanize(scheme) : 'Territoire';
}

/* Le profil de gisements : le rendement réel de CE monde, archétype x veines.
   C'est ce qui distingue deux planètes du même type. */
function renderDeposits() {
  const host = $('#terr-deposits');
  const yields = (state.territory && state.territory.yields) || {};
  const richness = (state.territory && state.territory.deposits) || {};
  const entries = Object.entries(yields).sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    host.innerHTML = '<span>Aucun gisement exploitable sur ce monde.</span>';
    return;
  }

  host.innerHTML =
    '<span>Gisements</span>' +
    entries
      .map(([key, factor]) => {
        const meta = RESOURCE_BY_KEY[key];
        // Au-delà du plafond de tirage ordinaire (1.25), c'est une veine riche.
        const rich = (richness[key] || 1) > 1.3;
        return `<span style="--dep-accent:var(--res-${esc(key)})" title="${esc(
          (meta && meta.label) || key
        )}">
        <b>${esc((meta && meta.label) || humanize(key))}</b>
        <span class="${rich ? 'rich' : ''}">×${esc(factor.toFixed(2))}${rich ? ' veine riche' : ''}</span>
      </span>`;
      })
      .join('');
}

/* ============================================================
   scène système
   ============================================================ */

async function selectTerritory(id, { push = true } = {}) {
  state.territoryId = id;
  state.tab = 'buildings';
  settledEvents = new Set();
  /* L'adresse d'abord : elle se lit dans l'etat, qui vient d'etre pose. */
  syncUrl({ replace: !push });
  stopMapTimers();
  showView('command');
  $('#tab-body').innerHTML = '<p class="empty">Chargement…</p>';
  await reloadTerritory(true);
  startTimers();
}

/* `force` : un changement de territoire ou une action doit passer même si
   une requête périodique est encore en vol. */
async function reloadTerritory(force = false) {
  const id = state.territoryId;
  if (!id) return;
  if (reloading && !force) return;
  reloading = true;
  try {
    await doReloadTerritory(id);
  } finally {
    reloading = false;
  }
}

async function doReloadTerritory(id) {
  let territory;
  try {
    territory = await api.territory(id);
  } catch (e) {
    handleApiError(e, 'Territoire indisponible');
    return;
  }

  /* Le reste est complémentaire : un échec ne doit pas vider la scène. */
  const systemId = territory.system ? territory.system.id : null;
  const [events, fleets, defenses, systemTerritories] = await Promise.all([
    api.territoryEvents(id).catch(() => []),
    systemId ? api.systemFleets(systemId).catch(() => []) : Promise.resolve([]),
    api.territoryDefenses(id).catch(() => []),
    systemId ? api.systemTerritories(systemId).catch(() => []) : Promise.resolve([]),
  ]);

  /* Le territoire a pu changer pendant les allers-retours : ne rien peindre
     par-dessus la sélection courante. */
  if (id !== state.territoryId) return;

  state.territory = territory;
  state.events = Array.isArray(events) ? events : [];
  state.fleets = Array.isArray(fleets) ? fleets : [];
  state.defenses = Array.isArray(defenses) ? defenses : [];
  state.systemTerritories = Array.isArray(systemTerritories) ? systemTerritories : [];

  renderCommand();
}

function handleApiError(e, context) {
  if (e instanceof ApiError && e.status === 401) {
    toast('Session expirée, reconnectez-vous.', 'err', 'Authentification');
    showView('login');
    return;
  }
  toast(e && e.message ? e.message : 'Erreur inattendue', 'err', context);
}

function renderCommand() {
  const t = state.territory;
  if (!t) return;

  // La galaxie surtitre le systeme : c'est la portee reelle du territoire.
  $('#galaxy-name').textContent = galaxyOf(t) || 'Système';
  $('#sys-name').textContent = (t.system && t.system.name) || `Système ${t.system ? t.system.id : '—'}`;
  $('#terr-title').textContent = `${territoryLabel(t)} · ${territorySubtitle(t)}`;
  const updated = parseUtc(t.updated_at);
  $('#terr-updated').textContent = updated ? `MAJ ${updated.toLocaleTimeString('fr-FR')}` : '';

  renderDeposits();
  renderHolding();
  renderResources();
  renderRail();
  renderTabs();
  renderTabBody();
}

/* Le bandeau de tenue : isolement, extinction, secession.

   **Muet tant que tout va bien.** Un bandeau qui annoncerait « raccorde » a
   chaque ouverture n'apprendrait rien et rendrait invisible celui qui annonce
   le contraire — c'est ainsi qu'on apprend a ignorer une alarme.

   Muet aussi quand le serveur ne dit rien : le bloc est absent sur un monde
   qui n'est pas a nous, et sur un serveur qui ne le connait pas encore. Se
   taire est le bon sens du repli. */
function renderHolding() {
  const host = $('#terr-holding');
  const h = (state.territory && state.territory.holding) || null;

  if (!h || !h.owned || (h.connected && !h.deactivated)) {
    host.classList.add('hidden');
    host.innerHTML = '';
    return;
  }

  host.classList.remove('hidden');
  host.classList.toggle('holding--dead', !!h.deactivated);

  const title = h.deactivated ? 'MONDE ÉTEINT' : 'COUPÉ DU RÉSEAU';
  const detail = h.deactivated
    ? `La stabilité est tombée à zéro : la production est arrêtée et tous les `
      + `chantiers sont gelés. ${secessionIn(h)} Nourrissez-le ou raccordez-le `
      + `et il remonte — il est encore à vous jusqu'à son départ.`
    : `Aucune route jusqu'à la capitale. La stabilité descend à chaque heure `
      + `passée ainsi, et un monde à zéro fait sécession trois jours plus tard `
      + `— avec tout ce qui y est entassé. Un dépôt aux deux bouts et un cargo `
      + `ouvrent la ligne.`;

  host.innerHTML = `<span class="ov">${esc(title)}</span>
    <p>${esc(detail)}</p>
    <button class="btn btn--sm" data-act="trade">Réseau de commerce</button>`;
}

/* Le compte a rebours, en clair. Le seul chiffre qui compte quand tout va mal. */
function secessionIn(holding) {
  const leaves = parseUtc(holding.secedes_at);
  if (!leaves) return 'La sécession peut tomber à tout moment.';

  const left = leaves.getTime() - Date.now();
  if (left <= 0) return 'La sécession peut tomber à tout moment.';

  const hours = Math.floor(left / 3600000);
  if (hours >= 24) {
    return `Sécession dans ${Math.floor(hours / 24)} j ${hours % 24} h.`;
  }
  if (hours >= 1) return `Sécession dans ${hours} h.`;
  return `Sécession dans ${Math.max(1, Math.round(left / 60000))} min.`;
}

/* ---------- bandeau de ressources ---------- */

function hourlyGains() {
  const totals = {};
  RESOURCES.forEach((r) => {
    totals[r.key] = 0;
  });
  Object.values((state.territory && state.territory.buildings) || {}).forEach((b) => {
    Object.entries(normalizeResourceMap(b.gain)).forEach(([k, v]) => {
      if (k in totals) totals[k] += v;
    });
  });
  return totals;
}

/* Douze ressources ne tiennent pas dans un bandeau lisible. On n'affiche un
   matériau que si le monde en produit ou s'il en reste en stock : la barre
   raconte alors ce qu'est la planète, au lieu d'aligner huit zéros. */
function visibleResources() {
  const res = (state.territory && state.territory.resources) || {};
  const yields = (state.territory && state.territory.yields) || {};
  return RESOURCES.filter(
    (r) => !r.empire && (!r.material || yields[r.key] > 0 || (res[r.key] || 0) > 0)
  );
}

function renderResources() {
  const res = (state.territory && state.territory.resources) || {};
  const yields = (state.territory && state.territory.yields) || {};
  const gains = hourlyGains();
  $('#res-grid').innerHTML = visibleResources()
    .map((r) => {
      const delta = gains[r.key] || 0;
      const barren = r.material && !(yields[r.key] > 0);
      const title = barren
        ? `${r.label} — non extractible sur ce monde`
        : r.label;
      return `<div class="chip${barren ? ' chip--barren' : ''}" style="--chip-accent:var(--res-${r.key})" title="${esc(title)}">
      <span class="k">${r.code}</span>
      <span class="v">${esc(fmtNumber(res[r.key] || 0))}</span>
      ${delta ? `<span class="d${delta < 0 ? ' neg' : ''}">${esc(fmtDelta(delta))}/h</span>` : ''}
    </div>`;
    })
    .join('');
}

/* ---------- rail d'orbites ---------- */

function renderRail() {
  const rail = $('#orbit-rail');
  const mine = new Set(state.myTerritories.map((t) => t.id));
  const list = state.systemTerritories.length ? state.systemTerritories : [state.territory];

  const orbs = [...list]
    .sort((a, b) => (a.position || 0) - (b.position || 0))
    .map((t) => {
      const owned = mine.has(t.id);
      const on = t.id === state.territoryId;
      return `<button class="orb${on ? ' on' : ''}${owned ? '' : ' foreign'}"
        data-orbit="${t.id}" data-owned="${owned ? '1' : '0'}"
        title="${esc(territoryLabel(t))}${owned ? '' : ' — hors de votre contrôle'}">
        <i style="background:${planetGradient(t.id || t.position || 1)}"></i>
        <b>${esc(roman(t.position || 1))}</b>
      </button>`;
    })
    .join('');

  rail.innerHTML = `<span class="ov" style="text-align:center">Orbites</span>${orbs}`;
}

/* ---------- onglets ---------- */

function renderTabs() {
  document.querySelectorAll('#tabs .tab').forEach((el) => {
    el.classList.toggle('on', el.dataset.tab === state.tab);
  });
}

function renderTabBody() {
  const host = $('#tab-body');
  if (state.tab === 'buildings') host.innerHTML = renderBuildings();
  else if (state.tab === 'shipyard') host.innerHTML = renderUnits('ship');
  else if (state.tab === 'fleets') host.innerHTML = renderFleets();
  else host.innerHTML = renderUnits('defense');
  updateProgressBars();
}

/* ============================================================
   flottes
   ============================================================
   Un vaisseau assemble ne reste pas sur la planete : il part en orbite, dans
   une flotte, et c'est la flotte qui porte une position — des coordonnees
   Unity que le serveur garde telles quelles. La console n'a pas de scene :
   elle montre ces coordonnees, elle n'en pose jamais.

   L'orbite est declaree et non deduite d'une distance, et c'est elle qui
   decide a quelle flotte revient un vaisseau qui sort de chantier : une seule
   flotte en orbite le prend, aucune ou plusieurs, le serveur en cree une. */

/* Les flottes qui tiennent l'orbite d'un territoire. */
function fleetsInOrbitOf(territoryId) {
  return state.fleets.filter((f) => f.orbiting_territory_id === territoryId);
}

/* Ce que le joueur a en orbite de la planete courante, par type. */
function shipsInOrbit() {
  const counts = {};
  fleetsInOrbitOf(state.territoryId).forEach((f) => {
    Object.entries(f.composition || {}).forEach(([type, n]) => {
      counts[type] = (counts[type] || 0) + n;
    });
  });
  return counts;
}

/* Ce que le joueur a dans tout le systeme, par type. */
function shipsInSystem() {
  const counts = {};
  state.fleets.forEach((f) => {
    Object.entries(f.composition || {}).forEach(([type, n]) => {
      counts[type] = (counts[type] || 0) + n;
    });
  });
  return counts;
}

function territoryById(id) {
  return (
    state.systemTerritories.find((t) => t.id === id)
    || (state.territory && state.territory.id === id ? state.territory : null)
  );
}

function orbitLabel(fleet) {
  /* « En transit » designait jusqu'ici une flotte sans orbite, ce qui etait deja
     approximatif — elle pouvait tres bien stationner sur place. Depuis qu'un
     vrai voyage existe, ce serait faux : on distingue les deux. */
  if (fleet.travel) return `En route vers le système ${fleet.travel.destination_id}`;
  if (!fleet.orbiting_territory_id) return 'Dans le système, sans orbite';
  const t = territoryById(fleet.orbiting_territory_id);
  return t ? `Orbite de ${territoryLabel(t)}` : `Orbite du territoire ${fleet.orbiting_territory_id}`;
}

/* L'etape du voyage et le temps restant, quand la flotte est en route.

   Le decompte part de `seconds_left` plutot que d'une comparaison avec
   `arriving_at` : l'heure d'arrivee est celle du serveur, et la pendule du
   navigateur n'a aucune raison de tomber d'accord avec elle. */
function travelMarkup(fleet) {
  if (!fleet.travel) return '';
  const t = fleet.travel;
  const hops = Array.isArray(t.route) ? t.route.length - 1 : 0;
  const done = (t.leg_index || 0) + 1;
  return `<div class="costs">
    <span class="cost">Saut <b>${esc(String(done))}/${esc(String(hops))}</b></span>
    <span class="cost">Arrivée dans <b>${esc(fmtDuration(t.seconds_left || 0))}</b></span>
    <span class="cost" title="Systèmes traversés">Route <b>${esc((t.route || []).join(' → '))}</b></span>
  </div>`;
}

function fmtPosition(p) {
  if (!p) return '—';
  const axis = (v) => (Math.round((Number(v) || 0) * 10) / 10).toLocaleString('fr-FR');
  return `${axis(p.x)} / ${axis(p.y)} / ${axis(p.z)}`;
}

function renderFleets() {
  if (!state.fleets.length) {
    return `<p class="empty">Aucune flotte dans ce système. Le premier vaisseau
      assemblé en fera naître une, en orbite de la planète qui l'a produit.</p>`;
  }

  const others = (fleet) => state.fleets.filter((f) => f.id !== fleet.id);

  return state.fleets
    .map((f) => {
      const here = f.orbiting_territory_id === state.territoryId;
      const composition = Object.entries(f.composition || {});

      /* Le transfert n'a de sens qu'avec une autre flotte pour destination :
         c'est le geste que reclame la regle de sortie de chantier, quand le
         serveur a cree une flotte neuve faute de pouvoir choisir. */
      const targets = others(f);
      const targetSelect = targets.length
        ? `<select class="qty" data-transfer-target="${f.id}" aria-label="Flotte destinataire">
            ${targets.map((t) => `<option value="${t.id}">${esc(t.name || `Flotte ${t.id}`)}</option>`).join('')}
          </select>`
        : '';

      const ships = composition.length
        ? composition
            .map(
              ([type, n]) => `<div class="row-head">
          <span class="ico">${icon(type)}</span>
          <span class="row-name">${esc(humanize(type))}</span>
          <span class="lvl">×${esc(fmtNumber(n))}</span>
          ${
            targets.length
              ? `<input class="qty" type="number" min="1" max="${n}" value="${n}"
                   data-transfer-qty="${f.id}-${esc(type)}" aria-label="Quantité à transférer">
                 <button class="btn btn--sm" data-transfer="${f.id}" data-type="${esc(type)}"
                   title="Transférer vers une autre flotte du système">Transférer</button>`
              : ''
          }
        </div>`
            )
            .join('')
        : '<p class="desc">Flotte vide.</p>';

      return `<div class="row">
      <div class="ico">${icon('fleet')}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(f.name || `Flotte ${f.id}`)}</span>
          <span class="lvl">${esc(fmtNumber(f.size || 0))} vaisseau(x)</span>
          <button class="btn btn--sm" data-fleet-rename="${f.id}">Renommer</button>
          ${
            f.travel
              ? `<button class="btn btn--sm" data-fleet-stop="${f.id}"
                   title="La flotte se pose au dernier relais franchi">Interrompre</button>`
              : here
                ? `<button class="btn btn--sm" data-fleet-orbit="${f.id}" data-territory="">Quitter l'orbite</button>`
                : `<button class="btn btn--sm" data-fleet-orbit="${f.id}" data-territory="${state.territoryId}">Amarrer ici</button>`
          }
          ${f.size || f.travel ? '' : `<button class="btn btn--sm" data-fleet-disband="${f.id}">Dissoudre</button>`}
        </div>
        <div class="costs">
          <span class="cost">${esc(orbitLabel(f))}</span>
          <span class="cost" title="Coordonnées Unity conservées par le serveur">Position <b>${esc(fmtPosition(f.position))}</b></span>
        </div>
        ${travelMarkup(f)}
        ${ships}
        ${targetSelect ? `<div class="costs"><span class="cost">Destinataire</span>${targetSelect}</div>` : ''}
      </div>
    </div>`;
    })
    .join('');
}

/* ---------- événements en cours ---------- */

function eventsOfType(type) {
  return state.events.filter((e) => bare(e.eventType) === type);
}

function eventFor(type, name) {
  return eventsOfType(type).find((e) => e.extraArgs && e.extraArgs.name === name) || null;
}

function eventProgress(ev) {
  const start = parseUtc(ev.createdAt);
  const end = parseUtc(ev.finishingAt);
  if (!start || !end) return { pct: 0, remaining: 0 };
  const total = end - start;
  const left = end - Date.now();
  if (total <= 0) return { pct: 100, remaining: 0 };
  return {
    pct: Math.min(100, Math.max(0, ((total - Math.max(0, left)) / total) * 100)),
    remaining: Math.max(0, left / 1000),
  };
}

function progressMarkup(ev, label) {
  if (!ev) return '';
  const { pct, remaining } = eventProgress(ev);
  return `<div class="bar" data-event="${ev.id}"><i style="width:${pct.toFixed(1)}%"></i></div>
    <div class="bar-label" data-event-label="${ev.id}">
      <span>${esc(label)}</span><span>${esc(fmtDuration(remaining))}</span>
    </div>`;
}

/* Rafraîchi chaque seconde sans rejouer le rendu complet. */
function updateProgressBars() {
  let justFinished = false;
  state.events.forEach((ev) => {
    const bar = document.querySelector(`.bar[data-event="${ev.id}"] i`);
    const label = document.querySelector(`[data-event-label="${ev.id}"] span:last-child`);
    if (!bar) return;
    const { pct, remaining } = eventProgress(ev);
    bar.style.width = `${pct.toFixed(1)}%`;
    if (label) label.textContent = fmtDuration(remaining);
    if (remaining <= 0 && !settledEvents.has(ev.id)) {
      settledEvents.add(ev.id);
      justFinished = true;
    }
  });
  return justFinished;
}

/* ---------- onglet Buildings ---------- */

function costMarkup(costs, resources) {
  return Object.entries(costs)
    .map(([key, value]) => {
      const meta = RESOURCES.find((r) => r.key === key);
      const affordable = (resources[key] || 0) >= value;
      return `<span class="cost${affordable ? '' : ' no'}">${esc(meta ? meta.label : humanize(key))} <b>${esc(
        fmtNumber(value)
      )}</b></span>`;
    })
    .join('');
}

function gainMarkup(gains) {
  return Object.entries(gains)
    .map(([key, value]) => {
      const meta = RESOURCES.find((r) => r.key === key);
      return `<span class="cost yield">${esc(meta ? meta.label : humanize(key))} <b>${esc(
        fmtDelta(value)
      )} / h</b></span>`;
    })
    .join('');
}

/* Pourquoi ce monde ne portera pas ce batiment, null s'il le porte.

   La regle vient du serveur, dans le bloc `construction` de la fiche : une
   plateforme orbitale n'a pas de sol pour une ferme, un monde sans hydrogene
   n'a rien a craquer. Recopiee ici, elle divergerait au premier equilibrage.

   Permissif quand le serveur ne dit rien : un serveur qui ne connait pas
   encore ce bloc ne doit pas faire disparaitre tous les batiments. Il
   refusera l'ordre lui-meme, comme avant. */
function placeRefusal(name) {
  const rules = (state.territory && state.territory.construction) || null;
  if (!rules || !Array.isArray(rules.accepts) || !rules.accepts.length) return null;
  if (rules.accepts.includes(name)) return null;

  const found = (rules.refusals || []).find((r) => r && r.name === name);
  return (found && found.reason) || 'Ce monde ne peut pas le porter.';
}

function renderBuildings() {
  const t = state.territory;
  const buildings = t.buildings || {};
  const resources = t.resources || {};
  const names = Object.keys(buildings).sort();
  if (!names.length) return '<p class="empty">Aucun bâtiment sur ce territoire.</p>';

  return names
    .map((name) => {
      const b = buildings[name];
      const costs = normalizeResourceMap(b.cost);
      const gains = normalizeResourceMap(b.gain);
      const affordable = Object.entries(costs).every(([k, v]) => (resources[k] || 0) >= v);
      const ev = eventFor('building', name);
      /* Un refus de PLACE n'est pas un manque du moment : rien ne le corrigera,
         ni d'attendre ni de chercher. La ligne est donc eteinte plutot
         qu'effacee — ne pas montrer la ferme laisserait la chercher — et sans
         ses couts : envoyer chercher du fer pour une ferme qu'aucune plateforme
         ne portera jamais est exactement ce que le serveur a cesse de faire. */
      const barred = placeRefusal(name);
      const cls = barred ? 'row barred' : ev ? 'row busy' : affordable ? 'row' : 'row off';

      return `<div class="${cls}">
      <div class="ico">${icon(name)}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(humanize(name))}</span>
          <span class="lvl">LVL ${esc(b.level)}</span>
          <button class="btn btn--sm${affordable && !ev && !barred ? ' btn--pri' : ''}"
            data-build-building="${esc(name)}" ${ev || !affordable || barred ? 'disabled' : ''}
            ${barred ? `title="${esc(barred)}"` : ''}>
            ${barred ? 'Impossible ici' : ev ? 'En cours' : 'Upgrade'}
          </button>
        </div>
        ${
          barred
            ? ''
            : `<div class="costs">
          ${costMarkup(costs, resources)}
          ${gainMarkup(gains)}
          <span class="cost">Durée <b>${esc(fmtDuration(b.duration))}</b></span>
        </div>`
        }
        <p class="desc${barred ? ' desc--barred' : ''}">${esc(
          barred || BUILDING_DESC[name] || 'Structure planétaire.'
        )}</p>
        ${barred ? '' : progressMarkup(ev, `Niveau ${Number(b.level) + 1} en construction`)}
      </div>
    </div>`;
    })
    .join('');
}

/* ---------- onglets Shipyard / Orbital Defences ---------- */

function renderUnits(kind) {
  const t = state.territory;
  const resources = t.resources || {};
  const catalog = kind === 'ship' ? state.catalog.ships : state.catalog.defenses;

  if (!catalog || !catalog.length) {
    return '<p class="empty">Catalogue indisponible.</p>';
  }

  /* Les defenses restent posees sur la planete ; les vaisseaux, non : ils
     partent en orbite dans une flotte. Le compteur montre donc ce qui tient
     l'orbite d'ici, et l'infobulle ce que porte tout le systeme. */
  const counts = kind === 'ship' ? shipsInOrbit() : {};
  const systemCounts = kind === 'ship' ? shipsInSystem() : {};
  if (kind === 'defense') {
    (state.defenses || []).forEach((u) => {
      counts[u.type] = u.quantity;
    });
  }

  const shipyardLevel = ((t.buildings || {}).shipyard || {}).level || 0;

  return catalog
    .map((u) => {
      const costs = normalizeResourceMap(u.cost);
      const affordable = Object.entries(costs).every(([k, v]) => (resources[k] || 0) >= v);
      const ev = eventFor(kind, u.name);
      /* Purement informatif : `Territory.build` ne vérifie que le coût,
         pas les prérequis technologiques. On n'interdit donc rien ici. */
      const locked = describeRequirements(u.requirements);
      const cls = ev ? 'row busy' : affordable ? 'row' : 'row off';
      const unitSeconds = u.integrity ? (u.integrity / 2500) * (1 + shipyardLevel) * 60 : 0;

      return `<div class="${cls}">
      <div class="ico">${icon(u.name)}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(humanize(u.name))}</span>
          <span class="lvl"${
            kind === 'ship'
              ? ` title="En orbite ici. Dans le système : ${esc(fmtNumber(systemCounts[u.name] || 0))}"`
              : ''
          }>×${esc(fmtNumber(counts[u.name] || 0))}</span>
          <input class="qty" type="number" min="1" max="999" value="1"
            data-qty="${esc(u.name)}" aria-label="Quantité ${esc(humanize(u.name))}">
          <button class="btn btn--sm${affordable ? ' btn--pri' : ''}"
            data-build-unit="${esc(u.name)}" data-kind="${kind}" ${affordable ? '' : 'disabled'}>
            Construire
          </button>
        </div>
        <div class="costs">
          ${costMarkup(costs, resources)}
          <span class="cost">Intégrité <b>${esc(fmtNumber(u.integrity || 0))}</b></span>
          ${unitSeconds ? `<span class="cost">Unité <b>${esc(fmtDuration(unitSeconds))}</b></span>` : ''}
        </div>
        <p class="desc">${esc(
          locked || `Coût unitaire. La durée d'assemblage dépend du niveau du chantier (LVL ${shipyardLevel}).`
        )}</p>
        ${progressMarkup(ev, `${(ev && ev.extraArgs && ev.extraArgs.quantity) || ''} restant(s) en assemblage`)}
      </div>
    </div>`;
    })
    .join('');
}

function describeRequirements(req) {
  if (!req || !req.technologies) return null;
  const parts = Object.entries(req.technologies).map(([k, v]) => `${humanize(k)} ${v}`);
  return parts.length ? `Requiert : ${parts.join(', ')}.` : null;
}

/* ============================================================
   actions
   ============================================================ */

async function upgradeBuilding(name) {
  try {
    await api.upgradeBuilding(state.territoryId, name);
    toast(`${humanize(name)} : construction lancée.`, 'info', 'Chantier');
    await reloadTerritory(true);
  } catch (e) {
    handleApiError(e, 'Construction refusée');
  }
}

async function buildUnit(kind, name, quantity) {
  const qty = Math.max(1, Math.min(999, Number(quantity) || 1));
  try {
    if (kind === 'ship') await api.buildShips(state.territoryId, name, qty);
    else await api.buildDefenses(state.territoryId, name, qty);
    toast(`${qty} × ${humanize(name)} : assemblage lancé.`, 'info', 'Chantier');
    await reloadTerritory(true);
  } catch (e) {
    handleApiError(e, 'Assemblage refusé');
  }
}

/* ---------- actions de flotte ---------- */

function fleetById(id) {
  return state.fleets.find((f) => f.id === id) || null;
}

async function runFleetAction(action, message) {
  try {
    await action();
    toast(message, 'info', 'Flottes');
    await reloadTerritory(true);
  } catch (e) {
    handleApiError(e, 'Flotte');
  }
}

function renameFleet(id) {
  const fleet = fleetById(id);
  const name = window.prompt('Nom de la flotte', (fleet && fleet.name) || '');
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    toast('Le nom ne peut pas être vide.', 'err', 'Flottes');
    return;
  }
  runFleetAction(() => api.renameFleet(id, trimmed), `Flotte renommée « ${trimmed} ».`);
}

/* territoryId vide = la flotte quitte l'orbite. C'est cette declaration qui
   dit au serveur ce qui se trouve en orbite quand un chantier livre : une
   flotte partie sans se detacher continuerait de recevoir. */
function setFleetOrbit(id, territoryId) {
  runFleetAction(
    () => api.orbitFleet(id, territoryId),
    territoryId ? 'Flotte amarrée en orbite.' : "Flotte détachée de son orbite."
  );
}

function disbandFleet(id) {
  runFleetAction(() => api.disbandFleet(id), 'Flotte dissoute.');
}

function stopFleetTravel(id) {
  runFleetAction(() => api.stopFleetTravel(id), 'Voyage interrompu.');
}

function transferShips(fleetId, type) {
  const target = document.querySelector(`[data-transfer-target="${fleetId}"]`);
  const qty = document.querySelector(`[data-transfer-qty="${CSS.escape(`${fleetId}-${type}`)}"]`);
  if (!target || !target.value) {
    toast('Aucune flotte destinataire dans ce système.', 'err', 'Flottes');
    return;
  }
  const quantity = Math.max(1, Number(qty ? qty.value : 1) || 1);
  runFleetAction(
    () => api.transferShips(fleetId, Number(target.value), type, quantity),
    `${quantity} × ${humanize(type)} transféré(s).`
  );
}

/* ============================================================
   minuteries
   ============================================================ */

function startTimers() {
  stopTimers();
  /* barres de progression : local, une fois par seconde */
  tickTimer = setInterval(() => {
    if (updateProgressBars()) reloadTerritory();
  }, 1000);
  /* état serveur : toutes les 30 s, pour les ressources produites */
  pollTimer = setInterval(reloadTerritory, 30000);
}

function stopTimers() {
  if (tickTimer) clearInterval(tickTimer);
  if (pollTimer) clearInterval(pollTimer);
  tickTimer = null;
  pollTimer = null;
}

/* ============================================================
   recherche — l'arbre technologique

   La recherche appartient au joueur, toutes galaxies confondues, et se paie sur
   l'ensemble de ses mondes : elle ne pouvait pas être un onglet de la fiche
   d'une planète. C'est donc une vue de premier niveau, montée sur la charpente
   de la carte de galaxie — rail, canevas, sélection — dont elle reprend les
   classes telles quelles.

   Deux lectures, et la séparation compte :

     · `/api/technologies/tree` publie la FORME de l'arbre — coûts, durées,
       prérequis, effets. Elle ne dépend d'aucun joueur et se lit une fois ;
     · `/api/technologies` publie l'ÉTAT du joueur dedans, et se relit à chaque
       geste.

   Rien des règles ne vit ici : ni le seuil d'un palier, ni le coût d'un niveau,
   ni la phrase qui décrit un effet. Tout vient du serveur, qui est celui qui
   les applique — une copie côté client finirait par décrire autre chose que ce
   que fait le calcul.
   ============================================================ */

/* Le dessin. Quatre colonnes, une par palier, dans un repère fixe : le cadre
   se redimensionne, le `viewBox` non. */
/* Des cartes assez grandes pour porter ce qu'on lit avant de cliquer : le nom
   sur deux lignes, le niveau, et l'effet en clair. À 152 × 56 il n'y tenait que
   le nom, et il fallait ouvrir chaque nœud pour savoir ce qu'il faisait. */
const NODE_W = 216;
const NODE_H = 92;
const NODE_CUT = 10;
const TIERS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

/* Une colonne par palier, à pas constant. Le dessin fait 2 700 unités de large :
   il ne tient dans aucun cadre de console, et le réduire jusqu'à l'y faire
   entrer rendrait les libellés illisibles. On le parcourt donc — molette pour
   zoomer, glisser pour déplacer — exactement comme la carte de la galaxie, dont
   ce canevas reprend la mécanique et les commandes.

   Le `viewBox` est la fenêtre courante, et non le dessin entier : zoomer, c'est
   la rétrécir ; se déplacer, c'est la faire glisser. Aucun point du tracé ne
   bouge. */
const TIER_PITCH = 268;
const TIER_X = TIERS.map((_, index) => 150 + index * TIER_PITCH);
const TREE_W = TIER_X[TIER_X.length - 1] + 150;
const TREE_H = 560;

const TREE_ZOOM_STEP = 1.25;

/* Deux seuils, et non un.
   ---
   Un seul seuil confondait deux questions différentes : « faut-il commencer à
   déplacer ? » et « ce relâchement était-il un clic ? ». À 4 px pour les deux,
   un clic dont la main dérivait de cinq pixels déplaçait l'arbre d'un cheveu et
   ne sélectionnait plus rien — la fiche restait sur le nœud précédent, et rien
   n'indiquait pourquoi. Sur ce canevas on clique bien plus qu'on ne déplace :
   c'est le clic qui doit être facile.

   Entre les deux valeurs, la vue bouge de quelques pixels ET le nœud se
   sélectionne. Un déplacement de six pixels ne valait de toute façon pas la
   peine d'être défendu. */
const TREE_PAN_START = 6;
const TREE_CLICK_SLOP = 14;
/* Bornes exprimées en largeur visible, ce qui se lit mieux qu'un facteur : au
   plus serré on voit deux colonnes et demie, au plus large l'arbre entier avec
   une marge. */
const TREE_VIEW_MIN = TIER_PITCH * 2.5;
const TREE_VIEW_MAX = TREE_W + 160;
/* Largeur visible à l'ouverture : quatre paliers, de quoi voir d'où l'on vient
   et où l'on va sans avoir à recadrer. */
const TREE_VIEW_DEFAULT = TIER_PITCH * 4;

/* Un noeud dont l'état ne change pas selon qu'on le regarde : c'est le serveur
   qui le nomme (`state` dans la charge utile), et le client ne fait que le
   traduire en classe. */
const NODE_STATE_LABEL = {
  maxed: 'Acquis — niveau maximum',
  researching: 'En recherche',
  locked: 'Verrouillé',
  owned: 'Acquis',
  available: 'Disponible',
};

const KIND_LABEL = {
  rank: 'Rang',
  breakthrough: 'Percée',
  doctrine: 'Doctrine',
  endless: 'Nœud infini',
};

function researchNode(name) {
  return state.research.nodes.get(name) || null;
}

function researchCard(name) {
  return state.research.cards.get(name) || null;
}

function branchMeta(key) {
  return state.research.branches.find((b) => b.name === key) || null;
}

/* ---------- entrée dans la vue ---------- */

async function openResearch({ push = true } = {}) {
  /* La recherche traverse les galaxies, mais l'adresse en porte une : c'est
     celle où l'on travaille, et c'est elle qui décide des mondes affichés
     partout ailleurs. */
  state.territoryId = null;
  state.research.open = true;
  syncUrl({ replace: !push });

  showView('research');
  $('#res-galaxy').textContent = state.galaxy || 'Empire';
  await loadResearch();
  startResearchTimers();
}

function leaveResearch() {
  state.research.open = false;
  stopResearchTimers();
}

async function loadResearch(force = false) {
  if (state.research.loading) return;
  state.research.loading = true;
  $('#research-updated').textContent = 'Lecture…';

  try {
    /* Le catalogue ne bouge pas d'une lecture à l'autre : on ne le redemande
       jamais une fois lu. L'état du joueur, si. */
    if (!state.research.tree || force) {
      const tree = await api.technologyTree();
      state.research.tree = tree;
      state.research.branches = tree.branches || [];
      state.research.tiers = tree.tiers || {};
      state.research.nodes = new Map((tree.nodes || []).map((n) => [n.name, n]));
    }

    const payload = await api.technologies();
    state.research.state = payload;
    state.research.cards = new Map(
      (payload.technologies || []).map((t) => [t.type, t])
    );
    state.research.readAt = Date.now();

    /* Le catalogue et l'état du joueur viennent de deux routes différentes, et
       rien ne garantit qu'ils décrivent le même arbre : le catalogue est bâti
       depuis le CODE, l'état depuis la BASE. Quand la base est en retard d'une
       migration, le canevas dessine des nœuds dont le joueur n'a aucun état —
       ils s'affichent, et cliquer dessus n'ouvre rien. Sans un mot.

       C'est le pire des comportements : l'écran a l'air cassé sans dire
       pourquoi. On compare donc les deux, et on nomme le désaccord. */
    const unknown = Array.from(state.research.nodes.keys()).filter(
      (name) => !state.research.cards.has(name)
    );
    state.research.unknown = new Set(unknown);
    if (unknown.length && !state.research.warned) {
      state.research.warned = true;
      toast(
        `Le catalogue annonce ${state.research.nodes.size} technologies, votre compte ` +
          `n'en porte que ${state.research.cards.size}. La base de données est en retard ` +
          `d'une migration : ces ${unknown.length} nœuds ne peuvent pas être ouverts.`,
        'err',
        'Recherche'
      );
    }

    if (!state.research.branch && state.research.branches.length) {
      state.research.branch = state.research.branches[0].name;
    }
    ensureResearchSelection();
    renderResearch();
    $('#research-updated').textContent = '';
  } catch (e) {
    $('#research-updated').textContent = '';
    handleApiError(e, 'Recherche');
  } finally {
    state.research.loading = false;
  }
}

/* La sélection suit la branche : au changement, on ouvre ce qui se passe —
   une recherche en cours, sinon le premier nœud à portée. Ouvrir une fiche
   vide obligerait à cliquer avant de pouvoir lire quoi que ce soit. */
function ensureResearchSelection() {
  const inBranch = nodesOfBranch(state.research.branch);
  if (!inBranch.length) {
    state.research.selected = null;
    return;
  }
  if (state.research.selected && inBranch.some((n) => n.name === state.research.selected)) {
    return;
  }
  const byState = (wanted) =>
    inBranch.find((n) => (researchCard(n.name) || {}).state === wanted);
  const pick = byState('researching') || byState('available') || byState('owned') || inBranch[0];
  state.research.selected = pick.name;
}

/* Tout l'amont d'un nœud : les nœuds qu'il faut avoir montés pour l'atteindre,
   et les liaisons qui les relient.

   On rend l'ENSEMBLE des ancêtres plutôt que la liste des chemins distincts.
   Un nœud profond en réclame deux ou trois, qui en réclament autant : énumérer
   les routes une par une en donnerait des dizaines, toutes composées des mêmes
   étapes. Ce que le joueur veut savoir est ce qu'il lui reste à monter, et
   c'est exactement cet ensemble — l'union de tous les chemins.

   Le niveau retenu pour chaque ancêtre est le PLUS ÉLEVÉ que réclame l'un de
   ses descendants sur le chemin : c'est lui qui contraint. Garder le premier
   rencontré ferait annoncer un objectif que le nœud suivant démentirait. */
function pathTo(name) {
  const need = new Map();
  const edges = new Set();
  const seen = new Set([name]);
  const queue = [name];

  while (queue.length) {
    const current = queue.shift();
    const node = researchNode(current);
    if (!node) continue;
    Object.entries(node.requires || {}).forEach(([required, level]) => {
      need.set(required, Math.max(need.get(required) || 0, level));
      edges.add(`${required}>${current}`);
      if (!seen.has(required)) {
        seen.add(required);
        queue.push(required);
      }
    });
  }

  return { need, edges };
}

/* Le chemin mis en ordre de parcours : par palier, puis par branche. C'est
   l'ordre dans lequel on peut réellement le monter, les paliers profonds
   n'ouvrant qu'après les précédents. */
function pathSteps(name) {
  const { need } = pathTo(name);
  return Array.from(need.entries())
    .map(([required, level]) => {
      const node = researchNode(required);
      const card = researchCard(required);
      const held = (card && card.level) || 0;
      return {
        name: required,
        node,
        level,
        held,
        done: held >= level,
        missing: Math.max(0, level - held),
      };
    })
    .filter((step) => step.node)
    .sort(
      (a, b) =>
        a.node.tier - b.node.tier || a.node.branch.localeCompare(b.node.branch)
    );
}

function nodesOfBranch(branch) {
  if (!branch) return [];
  return Array.from(state.research.nodes.values()).filter((n) => n.branch === branch);
}

/* ---------- rendu ---------- */

function renderResearch() {
  renderResearchPool();
  renderBranchRail();
  renderTree();
  renderNodeCard();
  renderResearchQueue();
}

/* La réserve de l'empire, et non celle d'un monde : c'est ce que la recherche
   regarde pour dire si un niveau est payable. */
function renderResearchPool() {
  const payload = state.research.state;
  if (!payload) return;

  const gain = payload.research_gain || 0;
  const chips = [
    `<div class="chip" style="--chip-accent:var(--res-research)" title="Données de recherche — produites par vos académies">
      <span class="k">DAT</span>
      <span class="v">${esc(fmtNumber(payload.research || 0))}</span>
      ${gain ? `<span class="d">${esc(fmtDelta(gain))}/h</span>` : ''}
    </div>`,
    `<div class="chip" title="Recherches menées de front">
      <span class="k">FILE</span>
      <span class="v">${esc(payload.used_slots || 0)} / ${esc(payload.slots || 0)}</span>
    </div>`,
  ];
  $('#research-pool').innerHTML = chips.join('');
}

function renderBranchRail() {
  const rail = $('#branch-rail');
  const totals = (state.research.state && state.research.state.branches) || {};

  const buttons = state.research.branches
    .map((branch) => {
      const spent = totals[branch.name] || 0;
      const tier = tierReached(spent);
      const on = branch.name === state.research.branch;
      return `<button class="brbtn" data-branch="${esc(branch.name)}"
        style="--h:${esc(branch.accent)}" aria-pressed="${on ? 'true' : 'false'}"
        title="${esc(branch.summary)}">
        <span class="bn">${esc(branch.label)}</span>
        <span class="bs">${esc(spent)} niv · palier ${esc(TIERS[tier - 1] || 'I')}</span>
      </button>`;
    })
    .join('');

  rail.innerHTML = `<span class="ov" style="text-align:center">Branches</span>${buttons}`;
}

/* Le palier atteint dans une branche, d'après les niveaux qu'on y a dépensés.
   Les seuils viennent du catalogue : le client ne les invente pas. */
function tierReached(spent) {
  const thresholds = state.research.tiers || {};
  let reached = 1;
  Object.entries(thresholds).forEach(([tier, needed]) => {
    if (spent >= needed) reached = Math.max(reached, Number(tier));
  });
  return reached;
}

/* Place les nœuds d'une branche : une colonne par palier, répartis en hauteur.
   Le dessin ne dit rien de plus que la table — il la rend lisible. */
function treeLayout(branch) {
  const nodes = nodesOfBranch(branch);
  const byTier = new Map();
  nodes.forEach((n) => {
    if (!byTier.has(n.tier)) byTier.set(n.tier, []);
    byTier.get(n.tier).push(n);
  });

  const positions = new Map();
  byTier.forEach((list, tier) => {
    const slice = (TREE_H - 40) / list.length;
    list.forEach((node, index) => {
      positions.set(node.name, {
        x: (TIER_X[tier - 1] || TIER_X[0]) - NODE_W / 2,
        y: 20 + slice * (index + 0.5) - NODE_H / 2,
      });
    });
  });
  return { nodes, positions };
}

/* Un rectangle à coin coupé, comme les panneaux du thème Nebula. La forme est
   la même pour tous les nœuds : ce qui les distingue est leur état, jamais leur
   silhouette. */
function cutBox(x, y, w, h, c) {
  return `${x + c},${y} ${x + w},${y} ${x + w},${y + h - c} ${x + w - c},${y + h} ${x},${y + h} ${x},${y + c}`;
}

/* Deux lignes au plus : les libellés du serveur vont jusqu'à « Intelligence
   artificielle », qui ne tient pas sur une. */
function wrapLabel(label, max = 17) {
  const words = String(label).split(' ');
  const lines = [''];
  words.forEach((word) => {
    const current = lines[lines.length - 1];
    if (!current) lines[lines.length - 1] = word;
    else if (`${current} ${word}`.length <= max) lines[lines.length - 1] = `${current} ${word}`;
    else if (lines.length < 2) lines.push(word);
    else lines[1] = `${lines[1]} ${word}`;
  });
  return lines.filter(Boolean);
}

function nodeBadge(node, card) {
  if (node.endless) return String(card.level || 0);
  if (node.kind === 'rank') return `${card.level || 0}/${node.max_level}`;
  if (node.kind === 'doctrine') return '◈';
  return card.level > 0 ? '✦' : '▣';
}

function renderTree() {
  const branch = branchMeta(state.research.branch);
  const frame = $('#tree-frame');
  if (!branch) {
    frame.innerHTML = '<p class="empty">Aucune branche.</p>';
    return;
  }

  $('#branch-title').textContent = branch.label;
  /* La légende se teinte comme la branche affichée : « acquis » se peint dans
     sa couleur, et il y en a cinq. Une pastille fixe aurait montré une teinte
     absente du dessin — une légende qui ne cite pas ses propres couleurs ne
     sert à rien. */
  const legend = $('#tree-legend');
  if (legend) legend.style.setProperty('--h', branch.accent);
  const spent = ((state.research.state || {}).branches || {})[branch.name] || 0;
  const reached = tierReached(spent);
  $('#branch-tiers').innerHTML = TIERS.map(
    (roman, index) =>
      `<span class="${index + 1 <= reached ? 'rich' : ''}">${roman}</span>`
  ).join(' · ');

  const { nodes, positions } = treeLayout(branch.name);
  const inBranch = new Set(nodes.map((n) => n.name));
  const parts = [];

  /* Le chemin vers la sélection : ses ancêtres et les liaisons qui y mènent.
     Ce qui n'en fait pas partie s'estompe — sans ce contraste, mettre le chemin
     en couleur ne fait qu'ajouter une couleur de plus sur un dessin qui en a
     déjà cinq. */
  const path = pathTo(state.research.selected);
  const onPath = (name) => path.need.has(name);

  /* La fenêtre survit aux relectures — le serveur est relu toutes les trente
     secondes, et repartir du cadrage par défaut à chaque fois ramènerait
     brutalement le joueur là où il n'était pas. Elle ne se repose que si l'on
     change de branche, ou à la toute première ouverture. */
  if (!state.research.view || state.research.viewBranch !== branch.name) {
    state.research.viewBranch = branch.name;
    centreOnSelected(positions, { keepZoom: false });
  }

  /* Les paliers : des bandes, et non un trait. Sur dix colonnes de cartes
     sombres, un filet vertical se perd ; une bande alternée donne à l'œil de
     quoi situer la profondeur sans rien suivre. Le chiffre est répété en haut
     et en bas — on ne voit jamais les deux bords à la fois. */
  TIER_X.forEach((x, index) => {
    const left = x - TIER_PITCH / 2;
    if (index % 2 === 1) {
      parts.push(
        `<rect class="tree-band" x="${left}" y="0" width="${TIER_PITCH}" height="${TREE_H}"/>`
      );
    }
    parts.push(
      `<text class="tree-tier-label" x="${x}" y="22">${TIERS[index]}</text>` +
        `<text class="tree-tier-label" x="${x}" y="${TREE_H - 10}">${TIERS[index]}</text>`
    );
  });

  /* Les liaisons d'abord : elles passent sous les nœuds. */
  nodes.forEach((node) => {
    const to = positions.get(node.name);
    Object.entries(node.requires || {}).forEach(([from, level]) => {
      const routed = path.edges.has(`${from}>${node.name}`);

      if (!inBranch.has(from)) {
        /* Un prérequis d'une autre branche : il entre par la gauche, sans
           origine visible — son nœud n'est pas sur ce dessin. La fiche, elle,
           le nomme et permet d'y aller. */
        const y = to.y + NODE_H / 2;
        const cls = `tree-link tree-link--foreign${routed ? ' tree-link--path' : ''}`;
        parts.push(
          `<path class="${cls}" d="M ${to.x - 46} ${y} H ${to.x - 4}"/>` +
            `<circle class="${cls}" cx="${to.x - 50}" cy="${y}" r="3"/>`
        );
        return;
      }
      const source = positions.get(from);
      const held = ((researchCard(from) || {}).level || 0) >= level;
      const x1 = source.x + NODE_W;
      const y1 = source.y + NODE_H / 2;
      const x2 = to.x;
      const y2 = to.y + NODE_H / 2;
      /* Une courbe, et non deux équerres. Un tracé à angle droit qui saute deux
         colonnes fait une longue verticale au milieu d'une pile de cartes : il
         passe dessous — les liaisons sont dessinées avant les nœuds — et paraît
         coupé en deux. Une courbe entre et sort par les côtés, là où on
         l'attend, et se suit du regard même quand elle disparaît un instant. */
      const bend = Math.max(34, (x2 - x1) * 0.45);
      parts.push(
        `<path class="tree-link${held ? ' tree-link--held' : ''}${
          routed ? ' tree-link--path' : ''
        }" style="--h:${esc(branch.accent)}"
          d="M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}"/>`
      );
    });
  });

  nodes.forEach((node) => {
    const card = researchCard(node.name) || { level: 0, state: 'locked' };
    const at = positions.get(node.name);
    const on = node.name === state.research.selected;
    const lines = wrapLabel(node.label, 21).slice(0, 2);

    const halo = on
      ? `<polygon class="tree-node__halo" points="${cutBox(
          at.x - 5, at.y - 5, NODE_W + 10, NODE_H + 10, NODE_CUT + 2
        )}"/>`
      : '';

    /* Deux noms au plus : au-delà, la ligne déborde de la carte, et savoir
       qu'un nœud ouvre trois choses vaut moins que de pouvoir les lire. Le
       reste est dans la fiche. */
    const opensAll = Object.values(node.unlocks || {})
      .flatMap((targets) => Object.keys(targets));
    const opens = opensAll.slice(0, 2);
    if (opensAll.length > opens.length) opens.push('+' + (opensAll.length - opens.length));

    /* La jauge ne dit quelque chose que sur un rang : une percée n'a pas de
       progression, elle est prise ou elle ne l'est pas. Elle cède la moitié de
       la ligne quand le nœud ouvre quelque chose — les deux partagent le bas de
       la carte, et pleine largeur elle passait sous le texte. */
    let gauge = '';
    if (node.kind === 'rank' && node.max_level) {
      const track = (NODE_W - 26) * (opens.length ? 0.42 : 1);
      const filled = Math.max(0, Math.min(1, (card.level || 0) / node.max_level));
      gauge =
        `<rect class="tree-node__track" x="${at.x + 13}" y="${at.y + NODE_H - 13}" width="${track.toFixed(
          1
        )}" height="4"/>` +
        `<rect class="tree-node__fill" x="${at.x + 13}" y="${at.y + NODE_H - 13}" width="${(
          track * filled
        ).toFixed(1)}" height="4"/>`;
    }

    /* Ce que le nœud fait, sur la carte et non dans la fiche : c'est la
       question qu'on se pose en survolant l'arbre, et devoir ouvrir chaque nœud
       pour y répondre était le vrai coût de lecture. */
    const effect = wrapLabel(nodeSummary(node), 30).slice(0, 2);
    const nameY = at.y + 26;
    const effectY = at.y + 32 + lines.length * 15;

    /* Trois états de mise en avant : la sélection, son amont, et le reste.
       Le reste ne s'estompe que s'il y a un amont — un nœud de départ n'a pas
       de chemin, et tout ternir autour de lui ne dirait rien. */
    const routed = onPath(node.name);
    const faded = path.need.size > 0 && !routed && !on;
    const orphan = state.research.unknown && state.research.unknown.has(node.name);

    parts.push(`<g class="tree-node tree-node--${esc(card.state)}${on ? ' tree-node--on' : ''}${
      routed ? ' tree-node--path' : ''
    }${faded ? ' tree-node--faded' : ''}${orphan ? ' tree-node--unknown' : ''}"
      style="--h:${esc(branch.accent)}" data-node="${esc(node.name)}"
      tabindex="0" role="button"
      aria-label="${esc(node.label)}, ${esc(NODE_STATE_LABEL[card.state] || '')}">
      ${halo}
      <polygon class="tree-node__box" points="${cutBox(at.x, at.y, NODE_W, NODE_H, NODE_CUT)}"/>
      <rect class="tree-node__edge" x="${at.x}" y="${at.y + NODE_CUT}" width="4" height="${NODE_H - NODE_CUT}"/>
      ${lines
        .map(
          (line, index) =>
            `<text class="tree-node__name" x="${at.x + 13}" y="${nameY + index * 15}">${esc(line)}</text>`
        )
        .join('')}
      ${effect
        .map(
          (line, index) =>
            `<text class="tree-node__effect" x="${at.x + 13}" y="${effectY + index * 13}">${esc(line)}</text>`
        )
        .join('')}
      <text class="tree-node__badge" x="${at.x + NODE_W - 12}" y="${at.y + 22}">${esc(
      nodeBadge(node, card)
    )}</text>
      ${
        opens.length
          ? `<text class="tree-node__opens" x="${at.x + NODE_W - 12}" y="${at.y + NODE_H - 12}">◆ ${esc(
              opens.join(' ')
            )}</text>`
          : ''
      }
      ${gauge}
    </g>`);
  });

  frame.innerHTML = `<svg viewBox="${viewBoxOf(state.research.view)}"
    preserveAspectRatio="xMidYMid meet" width="100%" height="100%" role="img"
    aria-label="Arbre technologique — branche ${esc(branch.label)}">${parts.join('')}</svg>`;
}

/* La phrase portée par la carte. L'effet d'un rang le décrit mieux que son
   résumé littéraire, qui est là pour la fiche ; une doctrine n'a que le sien,
   ses deux voies ne tenant pas sur une carte. */
function nodeSummary(node) {
  if (node.kind === 'doctrine') return 'Deux voies exclusives. Définitif.';
  const effect = (node.effects || [])[0];
  return effect ? effect.label : node.summary || '';
}

/* ---------- déplacement et zoom ----------

   Même mécanique que la carte de la galaxie, et pour la même raison : le dessin
   ne tient pas dans le cadre. Ce qui change est la fenêtre — le `viewBox` — et
   jamais le tracé.

   La hauteur de la fenêtre se déduit des proportions du cadre plutôt que d'être
   fixée : sans cela, un cadre large laisserait deux bandes vides au-dessus et
   au-dessous, `xMidYMid meet` centrant ce qu'il ne peut pas étirer. */
function treeSvg() {
  const frame = $('#tree-frame');
  return frame ? frame.querySelector('svg') : null;
}

function viewBoxOf(view) {
  const v = view || { x: 0, y: 0, w: TREE_W, h: TREE_H };
  return `${v.x.toFixed(2)} ${v.y.toFixed(2)} ${v.w.toFixed(2)} ${v.h.toFixed(2)}`;
}

function treeAspect() {
  const frame = $('#tree-frame');
  if (!frame) return 2.3;
  const rect = frame.getBoundingClientRect();
  return rect.height > 1 ? rect.width / rect.height : 2.3;
}

/* Pose la fenêtre autour d'un point, à une largeur voulue.

   Le centre est ramené dans le dessin, marge comprise : sans cette borne, un
   glissement un peu vif emmène l'arbre hors du cadre et il ne reste qu'un fond
   vide, sans rien qui indique de quel côté revenir. */
function setTreeView(centreX, centreY, width) {
  const w = Math.min(TREE_VIEW_MAX, Math.max(TREE_VIEW_MIN, width));
  const h = w / treeAspect();
  const cx = Math.min(TREE_W, Math.max(0, centreX));
  const cy = Math.min(TREE_H, Math.max(0, centreY));
  state.research.view = { x: cx - w / 2, y: cy - h / 2, w, h };
}

function applyTreeView() {
  const svg = treeSvg();
  if (svg && state.research.view) {
    svg.setAttribute('viewBox', viewBoxOf(state.research.view));
  }
}

/* Le point de l'arbre sous le pointeur. Même calcul que sur la carte, décalage
   de `meet` compris : les proportions de la fenêtre suivent celles du cadre,
   mais elles peuvent en différer le temps d'un redimensionnement. */
function treePointerPoint(ev) {
  const svg = treeSvg();
  const view = state.research.view;
  if (!svg || !view) return null;

  const rect = svg.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return null;

  const scale = Math.min(rect.width / view.w, rect.height / view.h);
  const originX = rect.left + (rect.width - view.w * scale) / 2;
  const originY = rect.top + (rect.height - view.h * scale) / 2;

  return {
    x: view.x + (ev.clientX - originX) / scale,
    y: view.y + (ev.clientY - originY) / scale,
    scale,
  };
}

/* Zoome autour d'un point, qui reste sous le pointeur : ce qu'on veut regarder
   est sous la souris, pas au milieu du cadre. */
function zoomTreeAround(point, factor) {
  const view = state.research.view;
  if (!view) return;

  const wanted = Math.min(TREE_VIEW_MAX, Math.max(TREE_VIEW_MIN, view.w / factor));
  if (Math.abs(wanted - view.w) < 1e-6) return;

  const ratioX = view.w > 0 ? (point.x - view.x) / view.w : 0.5;
  const ratioY = view.h > 0 ? (point.y - view.y) / view.h : 0.5;
  const h = wanted / treeAspect();

  state.research.view = {
    x: point.x - ratioX * wanted,
    y: point.y - ratioY * h,
    w: wanted,
    h,
  };
  applyTreeView();
}

function zoomTreeCentre(factor) {
  const view = state.research.view;
  if (!view) return;
  zoomTreeAround({ x: view.x + view.w / 2, y: view.y + view.h / 2 }, factor);
}

/* Recadrer : l'arbre entier, marges comprises. */
function fitTree() {
  setTreeView(TREE_W / 2, TREE_H / 2, TREE_VIEW_MAX);
  applyTreeView();
}

/* Amène la sélection au centre.

   Sans cela, changer de branche laisserait la fenêtre où la précédente l'avait
   laissée — et le nœud qu'on vient d'ouvrir serait hors champ, ce qui donne
   l'impression que la fiche parle d'autre chose. */
function centreOnSelected(positions, { keepZoom = true } = {}) {
  const at = positions.get(state.research.selected);
  if (!at) return;

  /* Largeur d'ouverture : quatre paliers, mais jamais moins que ce qu'il faut
     pour que les trois rangées tiennent en hauteur. Le cadre est deux fois plus
     large que haut et l'arbre cinq fois : à quatre paliers pile, la rangée du
     bas sortait du cadre, et rien n'indiquait qu'il en existait une. */
  const width = keepZoom && state.research.view
    ? state.research.view.w
    : Math.max(TREE_VIEW_DEFAULT, (TREE_H + 48) * treeAspect());

  /* Verticalement, on se cale sur le dessin tant qu'il tient tout entier :
     suivre la rangée du nœud choisi ferait sauter la vue d'un tiers de hauteur
     à chaque sélection, alors que tout est déjà visible. */
  const height = width / treeAspect();
  const centreY = height >= TREE_H ? TREE_H / 2 : at.y + NODE_H / 2;

  setTreeView(at.x + NODE_W / 2, centreY, width);
}

/* ---------- la fiche ---------- */

/* Le chemin d'accès, en clair.

   Le canevas montre la forme du chemin — quels nœuds, quelles liaisons — mais
   il n'en montre qu'une branche à la fois, et un chemin en traverse souvent
   deux ou trois. Cette liste-ci les porte toutes, dans l'ordre où on peut les
   monter, et chaque entrée ramène à son nœud.

   Les étapes déjà acquises restent affichées, barrées d'une coche : savoir ce
   qui est fait vaut autant que savoir ce qui reste, et les faire disparaître
   donnerait l'impression que le chemin change de forme à mesure qu'on avance. */
function pathMarkup(node, card) {
  const steps = pathSteps(node.name);
  if (!steps.length) return '';

  const remaining = steps.filter((step) => !step.done);
  const levels = remaining.reduce((sum, step) => sum + step.missing, 0);

  /* Le palier est une étape du chemin comme les autres, et souvent la dernière
     à tomber : il ne s'achète pas, il se traverse. */
  const tier = (card.missing || []).find((m) => m.kind === 'tier');

  const heading = remaining.length
    ? `${remaining.length} étape${remaining.length > 1 ? 's' : ''} · ${levels} niveau${
        levels > 1 ? 'x' : ''
      } à monter`
    : 'Chemin parcouru';

  /* Un nœud terminal a près de quarante ancêtres : la liste entière remplit le
     panneau et noie ce qui reste à faire. Au-delà d'une douzaine d'étapes, les
     acquises se replient derrière leur compte — un chemin court, lui, se lit
     tout entier, ce qui est le cas courant. */
  const folded = steps.length > 12 && remaining.length < steps.length;
  const shown = folded ? remaining : steps;

  const rows = shown
    .map((step) => {
      const foreign = step.node.branch !== node.branch;
      const branch = foreign ? branchMeta(step.node.branch) : null;
      return `<li class="path-step${step.done ? ' path-step--done' : ''}">
        <span class="path-tier">${TIERS[step.node.tier - 1]}</span>
        <button class="path-name" data-goto="${esc(step.name)}">${esc(step.node.label)}</button>
        ${branch ? `<span class="path-branch" style="--h:${esc(branch.accent)}">${esc(branch.label)}</span>` : ''}
        <span class="path-level">${step.done ? '✓' : `${step.held} / ${step.level}`}</span>
      </li>`;
    })
    .join('');

  const doneCount = steps.length - remaining.length;

  return `<div class="path">
    <span class="ov ov--mute">Chemin d'accès · ${esc(heading)}</span>
    ${
      folded
        ? `<p class="path-folded">${doneCount} étape${doneCount > 1 ? 's' : ''} déjà
             acquise${doneCount > 1 ? 's' : ''}, masquée${doneCount > 1 ? 's' : ''}.</p>`
        : ''
    }
    <ol class="path-list">${rows}</ol>
    ${
      tier
        ? `<p class="path-tier-note">Puis <b>${esc(tier.required)} niveaux</b> dépensés dans
             ${esc(tier.label)} pour ouvrir le palier — vous en avez ${esc(tier.held)}.</p>`
        : ''
    }
  </div>`;
}

function renderNodeCard() {
  const body = $('#node-body');
  const node = researchNode(state.research.selected);
  const card = researchCard(state.research.selected);

  if (!node) {
    $('#node-title').textContent = '—';
    $('#node-branch').textContent = 'Sélection';
    body.innerHTML = '<p class="empty">Choisissez un nœud dans l\'arbre.</p>';
    return;
  }

  /* Le nœud existe au catalogue mais le joueur n'en a aucun état : la base est
     en retard. On le dit ici, sur le nœud qu'on vient de cliquer, plutôt que de
     réafficher « Choisissez un nœud » — qui laisse croire que le clic n'a pas
     été reçu, et c'est exactement ce qu'on croyait. */
  if (!card) {
    const home = branchMeta(node.branch);
    $('#node-title').textContent = node.label;
    $('#node-branch').textContent = home ? home.label : node.branch;
    body.innerHTML = `<p class="empty">Ce nœud existe dans le catalogue du serveur,
      mais votre compte n'en porte aucun état : la base de données est en retard
      d'une migration. Il ne peut pas être ouvert tant qu'elle ne l'a pas
      rattrapée.</p>`;
    return;
  }

  const branch = branchMeta(node.branch);
  const pool = poolOfEmpire();
  $('#node-title').textContent = node.label;
  $('#node-branch').textContent = `${branch ? branch.label : node.branch} · palier ${
    TIERS[node.tier - 1]
  } · ${KIND_LABEL[node.kind] || node.kind}`;

  const parts = [`<div class="node-card" style="--h:${esc(branch ? branch.accent : 'var(--acc)')}">`];

  if (node.kind === 'rank' && node.max_level) {
    const segments = [];
    for (let i = 0; i < node.max_level; i += 1) {
      const filled = i < (card.level || 0);
      const queued = !filled && card.state === 'researching' && i === (card.level || 0);
      segments.push(`<i class="${filled ? 'f' : queued ? 'q' : ''}"></i>`);
    }
    parts.push(`<div class="lvl-strip">${segments.join('')}</div>`);
  }

  if (node.summary) parts.push(`<p class="desc">${esc(node.summary)}</p>`);

  /* Les effets, tels que le serveur les décrit : la phrase et le chiffre
     viennent du même calcul que celui qui les applique. */
  (card.effects || []).forEach((effect) => {
    const current = effect.current;
    const next = effect.next;
    const shows = current !== undefined && next !== undefined && current !== next;
    parts.push(`<div class="eff">${esc(effect.label)}${
      shows
        ? `<br><span class="now">actuel ${fmtSigned(current)}</span> → <span class="nxt">${fmtSigned(
            next
          )} au niveau suivant</span>`
        : ''
    }</div>`);
  });

  if (node.options && node.options.length) parts.push(doctrineMarkup(node, card));

  /* Ce qui permet d'AGIR d'abord : état, coût, bouton. Le chemin d'accès venait
     avant, et sur un nœud profond — vingt-huit étapes — il repoussait le bouton
     hors de l'écran. La fiche répondait alors à « comment y arriver » sans
     jamais répondre à « comment le lancer ». */
  parts.push(`<dl style="margin:0">
    <div class="node-kv"><dt>État</dt><dd>${esc(NODE_STATE_LABEL[card.state] || card.state)}</dd></div>
    <div class="node-kv"><dt>Niveau</dt><dd>${esc(levelLabel(node, card))}</dd></div>
    ${
      card.duration
        ? `<div class="node-kv"><dt>Durée</dt><dd>${esc(fmtDuration(card.duration))}</dd></div>`
        : ''
    }
  </dl>`);

  if (card.cost) {
    parts.push(`<div>
      <span class="ov" style="margin-bottom:6px">Coût du prochain niveau</span>
      <div class="node-costs">${costMarkup(card.cost, pool)}</div>
    </div>`);
  }

  parts.push(`<div class="node-actions">${nodeActionMarkup(node, card, pool)}</div>`);

  /* Ce que le nœud ouvre. Sans niveau : il l'ouvre au PREMIER, et les suivants
     n'ajoutent que de la puissance. La fiche annonçait « (niv. 6) » sur une
     coque qui restait invisible pendant cinq niveaux. */
  if (node.unlocks && Object.keys(node.unlocks).length) {
    const opened = Object.values(node.unlocks)
      .flatMap((targets) => Object.keys(targets))
      .map((name) => humanize(name));
    parts.push(`<p class="node-req node-req--opens">Ouvre dès le premier niveau :
      ${esc(opened.join(', '))}.</p>`);
  }

  /* Puis la référence : le chemin d'accès, qui remplace l'ancienne ligne
     « Exige ». Elle n'annonçait que le premier pas ; celui-ci dit tout ce qu'il
     reste, dans l'ordre où on peut le monter. */
  parts.push(pathMarkup(node, card));

  parts.push('</div>');
  body.innerHTML = parts.join('');
}

/* Ce sur quoi une recherche se facture : la réserve de Données de l'empire, et
   rien d'autre. Les Données n'appartiennent à aucune planète — c'est l'empire
   qui cherche et c'est lui qui paie.

   La somme des stocks de tous les mondes se faisait ici, parce qu'une
   recherche coûtait aussi des matériaux. Elle n'en coûte plus. */
function poolOfEmpire() {
  return { research: (state.research.state && state.research.state.research) || 0 };
}

function levelLabel(node, card) {
  if (card.state === 'maxed') return `${card.level} — maximum`;
  if (node.kind === 'rank' || node.endless) return `${card.level || 0} → ${(card.level || 0) + 1}`;
  return 'unique';
}

function fmtSigned(value) {
  const rounded = Math.round(value * 100) / 100;
  return `${rounded > 0 ? '+' : ''}${rounded} %`;
}

function doctrineMarkup(node, card) {
  const chosen = card.choice;
  const settled = Boolean(chosen) || card.state === 'researching';
  const options = node.options
    .map((option) => {
      const picked = option.key === chosen;
      const reachable = card.state !== 'locked';
      const effects = option.effects.map((e) => e.label).join(' · ');
      return `<button class="dopt${picked ? ' pick' : ''}"
        data-doctrine="${esc(option.key)}" ${settled || !reachable ? 'disabled' : ''}
        title="${esc(option.summary || '')}">
        <span class="dn">${esc(option.label)}${picked ? ' · retenue' : ''}</span>
        ${esc(effects)}
      </button>`;
    })
    .join('');
  const heading = settled
    ? 'Voie retenue'
    : card.state === 'locked'
    ? 'Deux voies exclusives — le choix se fera ici'
    : 'Choisissez une voie — définitif';
  return `<div class="doctrine">
    <span class="ov">${heading}</span>
    ${options}
  </div>`;
}

function nodeActionMarkup(node, card, pool) {
  if (card.state === 'maxed') {
    return '<button class="btn" disabled>Acquis</button>';
  }
  if (card.state === 'researching') {
    const event = pendingEventFor(node.name);
    return `<button class="btn" data-cancel-research="${esc(event ? event.id : '')}"
      ${event ? '' : 'disabled'}>Annuler — 50 % remboursé</button>`;
  }
  if (card.state === 'locked') {
    return '<button class="btn" disabled>Prérequis non atteints</button>';
  }

  const affordable = Object.entries(card.cost || {}).every(
    ([key, value]) => (pool[key] || 0) >= value
  );
  const full =
    (state.research.state.used_slots || 0) >= (state.research.state.slots || 0);

  if (full) {
    return '<button class="btn" disabled>Aucun emplacement libre</button>';
  }
  if (node.kind === 'doctrine' && !card.choice) {
    /* Le bouton reste, mais la voie se choisit au-dessus : le serveur refuse
       une doctrine sans voie, et l'interface doit dire pourquoi avant l'aller-
       retour. */
    return '<button class="btn" disabled>Choisissez une voie ci-dessus</button>';
  }
  return `<button class="btn${affordable ? ' btn--pri' : ''}"
    data-research="${esc(node.name)}" ${affordable ? '' : 'disabled'}>
    ${affordable ? 'Lancer la recherche' : 'Ressources insuffisantes'}
  </button>`;
}

function pendingEventFor(name) {
  return ((state.research.state && state.research.state.pending) || []).find(
    (e) => e.extraArgs && e.extraArgs.type === name
  );
}

/* ---------- la file ---------- */

function renderResearchQueue() {
  const payload = state.research.state;
  if (!payload) return;

  const rows = (payload.pending || [])
    .map((event) => {
      const args = event.extraArgs || {};
      const node = researchNode(args.type);
      const branch = node ? branchMeta(node.branch) : null;
      return `<div class="qrow" style="--h:${esc(branch ? branch.accent : 'var(--acc)')}"
        data-research-event="${esc(event.id)}">
        <span class="qn">${esc(args.label || humanize(args.type || ''))}
          <em>${esc((args.level || 1) - 1)} → ${esc(args.level || 1)}</em></span>
        <span class="bar"><i data-research-bar="${esc(event.id)}"
          data-created="${esc(event.createdAt)}" data-ends="${esc(event.finishingAt)}"></i></span>
        <span class="qt" data-research-left="${esc(event.finishingAt)}">—</span>
        <button class="btn btn--sm" data-cancel-research="${esc(event.id)}">Annuler</button>
      </div>`;
    })
    .join('');

  const free = Math.max(0, (payload.slots || 0) - (payload.pending || []).length);
  const slots = Array.from({ length: free })
    .map(
      () =>
        `<div class="qslot">Emplacement libre — une académie de plus tous les 10 niveaux</div>`
    )
    .join('');

  $('#research-queue').innerHTML =
    `<span class="ov">File de recherche · ${esc((payload.pending || []).length)} sur ${esc(
      payload.slots || 0
    )}</span>${rows}${slots}`;

  updateResearchBars();
}

/* Les comptes à rebours avancent sur l'horloge locale, comme ceux des
   chantiers : une lecture par seconde du serveur ne dirait rien de plus. Le
   retour à zéro déclenche une relecture, elle. */
function updateResearchBars() {
  const now = Date.now();
  let finished = false;

  document.querySelectorAll('[data-research-bar]').forEach((bar) => {
    const start = parseUtc(bar.dataset.created);
    const end = parseUtc(bar.dataset.ends);
    if (!start || !end) return;
    const total = end.getTime() - start.getTime();
    const done = total > 0 ? (now - start.getTime()) / total : 1;
    bar.style.width = `${Math.max(0, Math.min(100, done * 100)).toFixed(1)}%`;
  });

  document.querySelectorAll('[data-research-left]').forEach((label) => {
    const end = parseUtc(label.dataset.researchLeft);
    if (!end) return;
    const left = (end.getTime() - now) / 1000;
    label.textContent = left > 0 ? fmtDuration(left) : 'terminé';
    if (left <= 0) finished = true;
  });

  return finished;
}

/* ---------- actions ---------- */

async function startResearch(name) {
  const card = researchCard(name);
  try {
    await api.research(name, (card && card.choice) || null);
    const node = researchNode(name);
    toast(`${(node && node.label) || humanize(name)} : recherche lancée.`, 'info', 'Recherche');
    await loadResearch();
  } catch (e) {
    handleApiError(e, 'Recherche refusée');
  }
}

async function cancelResearch(eventId) {
  try {
    await api.cancelResearch(Number(eventId));
    toast('Recherche annulée, la moitié de la dépense est rendue.', 'info', 'Recherche');
    await loadResearch();
  } catch (e) {
    handleApiError(e, 'Annulation refusée');
  }
}

/* Le choix d'une voie n'est pas envoyé seul : il est porté par la commande. On
   le retient localement le temps de cliquer sur « Lancer », et l'interface
   montre laquelle est armée. */
function armDoctrine(key) {
  const card = researchCard(state.research.selected);
  /* Verrouille compris : armer une voie sur un noeud hors d'atteinte laisserait
     croire que le choix est fait, alors que rien ne sera commande. */
  if (!card || card.state === 'researching' || card.state === 'maxed') return;
  if (card.state === 'locked') return;
  card.choice = card.choice === key ? null : key;
  renderNodeCard();
}

function selectResearchNode(name) {
  if (!state.research.nodes.has(name)) return;
  state.research.selected = name;
  renderTree();
  renderNodeCard();
}

/* Ouvre un nœud et l'amène sous les yeux : utilisé par les prérequis de la
   fiche, qui désignent des nœuds souvent hors du cadre. */
function revealResearchNode(name) {
  if (!state.research.nodes.has(name)) return;
  const node = researchNode(name);
  if (node.branch !== state.research.branch) {
    state.research.branch = node.branch;
    state.research.viewBranch = null;
    renderBranchRail();
  }
  state.research.selected = name;
  const positions = treeLayout(state.research.branch).positions;
  centreOnSelected(positions);
  renderTree();
  renderNodeCard();
}

function selectBranch(name) {
  if (state.research.branch === name) return;
  state.research.branch = name;
  ensureResearchSelection();
  renderBranchRail();
  renderTree();
  renderNodeCard();
}

function startResearchTimers() {
  stopResearchTimers();
  researchTimer = setInterval(() => {
    if (updateResearchBars()) loadResearch();
    if (state.research.tick++ % 30 === 29) loadResearch();
  }, 1000);
}

function stopResearchTimers() {
  if (researchTimer) clearInterval(researchTimer);
  researchTimer = null;
}

/* Déplacement et zoom, branchés à l'identique de la carte de la galaxie : deux
   canevas qui se parcourent de la même façon n'en font qu'un à apprendre. */
function initTreeNavigation() {
  const frame = $('#tree-frame');
  if (!frame) return;

  on('#tree-zoom-in', 'click', () => zoomTreeCentre(TREE_ZOOM_STEP));
  on('#tree-zoom-out', 'click', () => zoomTreeCentre(1 / TREE_ZOOM_STEP));
  on('#tree-fit', 'click', fitTree);
  on('#tree-focus', 'click', () => {
    const branch = branchMeta(state.research.branch);
    if (!branch) return;
    centreOnSelected(treeLayout(branch.name).positions, { keepZoom: false });
    applyTreeView();
  });

  /* `passive: false` : sans cela le navigateur refuse l'annulation et la page
     défile pendant qu'on zoome. */
  frame.addEventListener(
    'wheel',
    (ev) => {
      if (!state.research.view) return;
      ev.preventDefault();
      const point = treePointerPoint(ev);
      if (!point) return;
      zoomTreeAround(point, ev.deltaY < 0 ? TREE_ZOOM_STEP : 1 / TREE_ZOOM_STEP);
    },
    { passive: false }
  );

  let drag = null;

  frame.addEventListener('pointerdown', (ev) => {
    if (!state.research.view || ev.button !== 0) return;
    const point = treePointerPoint(ev);
    if (!point) return;

    drag = {
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
      viewX: state.research.view.x,
      viewY: state.research.view.y,
      scale: point.scale,
      captured: false,
      panning: false,
      /* Course maximale depuis l'appui : c'est elle, et non le seul fait
         d'avoir déplacé, qui décide si le relâchement était un clic. */
      moved: 0,
    };
    state.research.dragged = false;
    /* Pas de capture ici : `setPointerCapture` réoriente aussi les `click` qui
       suivent, et la cible deviendrait le cadre — `closest('[data-node]')` ne
       trouverait plus rien et un simple clic cesserait de sélectionner. On ne
       prend le pointeur qu'au moment où un vrai glissement commence. */
  });

  frame.addEventListener('pointermove', (ev) => {
    if (!drag || ev.pointerId !== drag.pointerId) return;

    const dx = ev.clientX - drag.startX;
    const dy = ev.clientY - drag.startY;
    /* Distance vraie, et non `|dx| + |dy|` : cette dernière compte une dérive
       en diagonale une fois et demie ce qu'elle vaut, et un clic de biais était
       donc plus vite refusé qu'un clic droit. */
    drag.moved = Math.max(drag.moved, Math.hypot(dx, dy));

    /* En deçà, la main n'a pas encore quitté son point d'appui. */
    if (!drag.panning && drag.moved < TREE_PAN_START) return;

    if (!drag.panning) {
      drag.panning = true;
      frame.classList.add('map-frame--panning');
    }

    /* On déplace dès six pixels, mais on ne renonce au clic qu'à quatorze : le
       geste hésitant fait les deux, ce qui est exactement ce qu'on en attend. */
    if (drag.moved > TREE_CLICK_SLOP && !drag.captured) {
      /* La capture arrive ICI, et pas au premier pixel de déplacement.
         `setPointerCapture` réoriente vers l'élément capturant non seulement
         les événements de pointeur mais aussi le `click` qui suit : la cible
         devient le cadre, et `closest('[data-node]')` ne trouve plus rien.
         Capturer dès le début du déplacement rendait donc TOUT clic un peu
         glissé inopérant, quel que soit le seuil qu'on mettait ailleurs — le
         nœud n'était plus la cible, il n'y avait plus rien à sélectionner.

         Sous ce seuil, la capture ne manque à personne : le pointeur n'a pas
         bougé assez pour sortir du cadre. */
      state.research.dragged = true;
      try {
        frame.setPointerCapture(ev.pointerId);
        drag.captured = true;
      } catch (e) {
        /* capture refusée : le glissement marche tant que le pointeur reste
           dans le cadre, ce qui est le cas courant */
      }
    }

    state.research.view.x = drag.viewX - dx / drag.scale;
    state.research.view.y = drag.viewY - dy / drag.scale;
    applyTreeView();
  });

  const endDrag = (ev) => {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    if (drag.captured) {
      try {
        frame.releasePointerCapture(ev.pointerId);
      } catch (e) {
        /* le pointeur a pu être perdu en route */
      }
    }
    drag = null;
    frame.classList.remove('map-frame--panning');
  };

  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);

  /* Les proportions de la fenêtre suivent celles du cadre : sans cela, replier
     le navigateur laisserait des bandes vides jusqu'au prochain rendu. */
  window.addEventListener('resize', () => {
    if (!state.research.open || !state.research.view) return;
    const view = state.research.view;
    setTreeView(view.x + view.w / 2, view.y + view.h / 2, view.w);
    applyTreeView();
  });
}

function initResearch() {
  /* La sélection d'abord, la navigation ensuite. C'est le geste principal de
     l'écran : il ne doit pas pouvoir tomber avec un bouton de zoom. */
  on('#branch-rail', 'click', (ev) => {
    const button = ev.target.closest('[data-branch]');
    if (button) selectBranch(button.dataset.branch);
  });

  on('#tree-frame', 'click', (ev) => {
    /* Un clic qui clôt un glissement ne désigne rien : on vient de déplacer
       l'arbre. Sans ce garde, relâcher au-dessus d'un nœud le sélectionnerait
       au passage. */
    if (state.research.dragged) {
      state.research.dragged = false;
      return;
    }
    const node = ev.target.closest('[data-node]');
    if (node) selectResearchNode(node.dataset.node);
  });

  /* Le graphe se parcourt au clavier : les nœuds portent `tabindex`, encore
     faut-il que la touche fasse ce que le clic fait. */
  on('#tree-frame', 'keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const node = ev.target.closest('[data-node]');
    if (!node) return;
    ev.preventDefault();
    selectResearchNode(node.dataset.node);
  });

  on('#node-body', 'click', (ev) => {
    const goto = ev.target.closest('[data-goto]');
    if (goto) {
      revealResearchNode(goto.dataset.goto);
      return;
    }
    const doctrine = ev.target.closest('[data-doctrine]');
    if (doctrine && !doctrine.disabled) {
      armDoctrine(doctrine.dataset.doctrine);
      return;
    }
    const start = ev.target.closest('[data-research]');
    if (start) {
      startResearch(start.dataset.research);
      return;
    }
    const cancel = ev.target.closest('[data-cancel-research]');
    if (cancel && cancel.dataset.cancelResearch) {
      cancelResearch(cancel.dataset.cancelResearch);
    }
  });

  on('#research-queue', 'click', (ev) => {
    const cancel = ev.target.closest('[data-cancel-research]');
    if (cancel && cancel.dataset.cancelResearch) {
      cancelResearch(cancel.dataset.cancelResearch);
    }
  });

  /* En dernier : déplacement et zoom sont un confort, la sélection est l'écran.
     Ce qui peut tomber tombe après ce qui ne le doit pas. */
  initTreeNavigation();
}

/* ============================================================
   câblage
   ============================================================ */

function initEvents() {
  $('#tabs').addEventListener('click', (ev) => {
    const tab = ev.target.closest('.tab');
    if (!tab) return;
    state.tab = tab.dataset.tab;
    renderTabs();
    renderTabBody();
  });

  $('#orbit-rail').addEventListener('click', (ev) => {
    const orb = ev.target.closest('.orb');
    if (!orb) return;
    const id = Number(orb.dataset.orbit);

    /* Un monde qu'on ne tient pas n'est plus une impasse : c'est la seule
       facon d'etendre un empire, et la console ne savait que la refuser. Le
       serveur dit, monde par monde, ce qu'il faudrait pour le prendre. */
    if (orb.dataset.owned !== '1') {
      openClaim(id);
      return;
    }
    if (id !== state.territoryId) selectTerritory(id);
  });

  $('#tab-body').addEventListener('click', (ev) => {
    const building = ev.target.closest('[data-build-building]');
    if (building) {
      upgradeBuilding(building.dataset.buildBuilding);
      return;
    }
    const unit = ev.target.closest('[data-build-unit]');
    if (unit) {
      const name = unit.dataset.buildUnit;
      const input = document.querySelector(`[data-qty="${CSS.escape(name)}"]`);
      buildUnit(unit.dataset.kind, name, input ? input.value : 1);
      return;
    }

    const rename = ev.target.closest('[data-fleet-rename]');
    if (rename) {
      renameFleet(Number(rename.dataset.fleetRename));
      return;
    }
    const orbit = ev.target.closest('[data-fleet-orbit]');
    if (orbit) {
      const target = orbit.dataset.territory;
      setFleetOrbit(Number(orbit.dataset.fleetOrbit), target ? Number(target) : null);
      return;
    }
    const stop = ev.target.closest('[data-fleet-stop]');
    if (stop) {
      stopFleetTravel(Number(stop.dataset.fleetStop));
      return;
    }
    const disband = ev.target.closest('[data-fleet-disband]');
    if (disband) {
      disbandFleet(Number(disband.dataset.fleetDisband));
      return;
    }
    const transfer = ev.target.closest('[data-transfer]');
    if (transfer) {
      transferShips(Number(transfer.dataset.transfer), transfer.dataset.type);
    }
  });

  $('#pick-list').addEventListener('click', (ev) => {
    const pick = ev.target.closest('[data-territory]');
    if (pick) {
      selectTerritory(Number(pick.dataset.territory));
      return;
    }
    if (ev.target.closest('[data-action="logout"]')) logout();
  });

  $('#login-galaxy').addEventListener('change', (ev) => {
    state.galaxy = ev.target.value || null;
    /* Avant connexion, l'adresse suit sans empiler : le joueur essaie des
       galaxies dans une liste, il ne navigue pas. */
    syncUrl({ replace: true });
    fillGalaxySelect($('#pick-galaxy'));
  });
  $('#pick-galaxy').addEventListener('change', (ev) => switchGalaxy(ev.target.value));

  // Retour arriere du navigateur : l'adresse fait foi, et on ne la reecrit pas
  // en repondant — ce serait empiler une entree par pas en arriere.
  window.addEventListener('popstate', () => {
    applyRoute({ push: false });
  });

}

/* ============================================================
   barre du haut : commandes, menu, paramètres

   Elle alignait cinq boutons de même poids — dont un rouge — pour trois gestes
   quotidiens et trois qu'on ne fait presque jamais. Rien ne distinguait
   « rafraîchir », qu'on fait dix fois par minute, de « déconnexion », qu'on fait
   une fois par jour et jamais par erreur.

   Ce qui est courant devient une icône, ce qui est rare passe sous un menu. Les
   boutons sont désignés par leur action et non par un identifiant : les deux
   scènes portent la même barre, et un identifiant par bouton et par scène
   aurait fait deux jeux de branchements à tenir en accord.
   ============================================================ */

const CHROME_ICONS = {
  map: 'galaxy',
  research: 'research',
  worlds: 'worlds',
  'refresh-territory': 'refresh',
  'refresh-map': 'refresh',
  'refresh-research': 'refresh',
  moderation: 'sliders',
  settings: 'settings',
  logout: 'logout',
};

/* Les pictogrammes sont posés une fois. Le titre porte le libellé : un bouton
   qui n'est qu'une icône doit pouvoir se nommer, au survol comme au lecteur
   d'écran, d'où le `aria-label` dans le balisage. */
function paintChrome() {
  document.querySelectorAll('[data-menu-toggle]').forEach((button) => {
    if (!button.querySelector('svg')) button.innerHTML = icon('menu');
  });

  document.querySelectorAll('[data-act]').forEach((button) => {
    const name = CHROME_ICONS[button.dataset.act];
    if (!name || button.querySelector('svg')) return;
    button.insertAdjacentHTML('afterbegin', icon(name));
  });
}

function closeMenus() {
  document.querySelectorAll('[data-menu]').forEach((menu) => {
    const pop = menu.querySelector('[data-menu-pop]');
    const toggle = menu.querySelector('[data-menu-toggle]');
    if (pop) pop.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  });
}

function menusOpen() {
  return Array.from(document.querySelectorAll('[data-menu-pop]')).some((p) => !p.hidden);
}

function openSettings() {
  $('#modal-settings').classList.remove('hidden');
}

function closeSettings() {
  $('#modal-settings').classList.add('hidden');
}

function settingsOpen() {
  return !$('#modal-settings').classList.contains('hidden');
}

/* ============================================================
   appareils enregistrés

   Le client de jeu range une clé d'appareil pour ne plus redemander de mot de
   passe au démarrage. Cette console est le seul endroit d'où elle peut être
   retirée : le jeu ne connaît que la machine sur laquelle il tourne, et une clé
   laissée sur un poste qu'on ne reverra pas resterait valable jusqu'à son
   échéance — trois mois.

   Le serveur ne rend jamais la valeur d'une clé : il n'en garde que
   l'empreinte. Ce qui s'affiche ici sert à reconnaître une machine et à la
   fermer, rien d'autre.
   ============================================================ */

/* ============================================================
   prendre un monde

   Trois gestes derriere une seule route : s'installer pour la premiere fois,
   coloniser un monde solide, arrimer une plateforme au-dessus d'un corps sans
   surface. C'est le serveur qui decide lequel se joue, et c'est lui qui dit ce
   qui manque — la console n'a aucune regle d'archetypes a recopier, et ne doit
   pas en inventer une : celle-ci a deja change deux fois.
   ============================================================ */

/* Le libelle du geste. Le serveur nomme `colony` ou `station` ; ce qu'un joueur
   lit doit dire ce qu'il va FAIRE. */
const CLAIM_KIND = {
  colony: 'Coloniser',
  station: 'Arrimer une plateforme',
};

function openClaim(id) {
  const t = (state.systemTerritories || []).find((x) => x.id === id);
  if (!t) {
    toast('Ce monde est inconnu de la vue courante.', 'err', 'Orbite');
    return;
  }

  $('#modal-claim').classList.remove('hidden');
  renderClaim(t);
}

function closeClaim() {
  $('#modal-claim').classList.add('hidden');
}

function claimOpen() {
  return !$('#modal-claim').classList.contains('hidden');
}

function renderClaim(t) {
  const offer = t.claim || null;
  $('#claim-title').textContent = `${territoryLabel(t)} · ${territorySubtitle(t)}`;
  $('#claim-kind').textContent =
    (offer && CLAIM_KIND[offer.kind]) || 'Monde';

  const host = $('#claim-body');

  if (!offer) {
    /* Serveur trop ancien pour le dire : on ne devine pas a sa place. */
    host.innerHTML = `<p class="empty">Ce serveur ne dit pas ce qu'il faudrait
      pour prendre ce monde.</p>`;
    return;
  }

  if (offer.taken) {
    host.innerHTML = `<p class="empty">Ce monde appartient déjà à quelqu'un.</p>`;
    return;
  }

  /* Ce qu'il faut avoir : une coque en orbite, et parfois des technologies.
     La premiere prise d'une galaxie ne demande rien — on ne peut pas exiger un
     vaisseau de quelqu'un qui n'a encore aucun chantier. */
  const needs = [];
  if (offer.hull) {
    needs.push(`<li><b>${esc(humanize(offer.hull))}</b> en orbite de ce monde.
      La coque est consommée : elle devient l'installation.</li>`);
  }
  (offer.requires_list || []).forEach((r) => {
    needs.push(`<li>Technologie <b>${esc(humanize(r.name))} ${esc(r.level)}</b>.</li>`);
  });

  const hint =
    offer.kind === 'station'
      ? `Ce corps n'a pas de sol : on ne s'y pose pas, on s'y amarre. La
         plateforme n'abrite personne — pas de population, donc pas de famine —
         et ne porte que des modules : extraction, énergie, dépôt, craquage.`
      : `Un monde solide se colonise : le vaisseau y débarque ses colons et
         devient la colonie.`;

  host.innerHTML = `
    <p class="mod-intro">${hint}</p>
    ${offer.first ? `<p class="mod-intro">Première prise dans cette galaxie :
       elle ne coûte rien, et fera votre capitale — le point fixe depuis lequel
       se mesure le raccordement de tous vos autres mondes.</p>` : ''}
    ${needs.length ? `<ul class="claim-needs">${needs.join('')}</ul>` : ''}
    ${
      offer.available
        ? ''
        : `<p class="claim-refusal">${esc(offer.refusal || 'Impossible pour le moment.')}</p>`
    }
    <div class="rule"></div>
    <button class="btn btn--sm${offer.available ? ' btn--pri' : ''}"
      id="claim-go" ${offer.available ? '' : 'disabled'}>
      ${esc((CLAIM_KIND[offer.kind] || 'Prendre ce monde'))}
    </button>`;

  const go = $('#claim-go');
  if (go && offer.available) {
    go.addEventListener('click', () => claimWorld(t.id));
  }
}

async function claimWorld(id) {
  const button = $('#claim-go');
  if (button) button.disabled = true;

  try {
    await api.claimTerritory(id);
    toast('Monde pris.', 'info', 'Expansion');
    closeClaim();
    /* Les mondes du joueur ont change : la liste sert au rail, a la carte et
       au reseau de commerce. */
    state.myTerritories = await api.myTerritories(state.galaxy).catch(() => state.myTerritories);
    await selectTerritory(id);
  } catch (e) {
    if (button) button.disabled = false;
    /* Le refus vient du serveur, mot pour mot : il nomme la coque manquante ou
       la technologie qui n'est pas atteinte. */
    handleApiError(e, 'Prise refusée');
  }
}

/* ============================================================
   reseau de commerce

   Un monde coupe du reseau imperial perd de la stabilite a chaque heure,
   s'eteint a zero, et fait secession trois jours plus tard en emportant tout ce
   qu'on y avait entasse. Une ligne de commerce est la SEULE reponse a cela.

   Ce que la vue montre en premier n'est donc pas la liste des lignes : ce sont
   les mondes coupes, avec leur compte a rebours. C'est la question qu'on vient
   poser ici, et une liste de routes n'y repond pas.

   La console ne decide de rien : ce qui circule vient du serveur, les refus
   aussi, mot pour mot.
   ============================================================ */

/* Les flux en cours d'edition, par ligne. Gardes a part de la reponse serveur :
   le joueur en declare plusieurs avant d'envoyer, et une relecture tombant
   entre-temps effacerait sa saisie. */
let tradeDrafts = new Map();

let tradeState = { lines: [], tradeable: [] };

const BLOCKADE_HINT =
  "Une flotte étrangère tient un bout. Rien n'est détruit : la ligne coule de "
  + "nouveau dès qu'elle s'en va — mais en attendant, le monde au bout compte "
  + 'comme isolé.';

async function openTrade() {
  closeMenus();
  $('#modal-trade').classList.remove('hidden');
  $('#trade-body').innerHTML = '<p class="empty">Chargement…</p>';
  await loadTrade();
}

function closeTrade() {
  $('#modal-trade').classList.add('hidden');
}

function tradeOpen() {
  return !$('#modal-trade').classList.contains('hidden');
}

async function loadTrade() {
  /* Les mondes ET les lignes, dans cet ordre : la vue croise l'un avec
     l'autre — qui est coupe, qui est deja relie. Une moitie fraiche et l'autre
     perimee donnerait des avertissements faux. */
  try {
    const [mine, payload] = await Promise.all([
      api.myTerritories(state.galaxy).catch(() => state.myTerritories),
      api.tradeLines(),
    ]);

    if (Array.isArray(mine)) state.myTerritories = mine;
    tradeState = {
      lines: (payload && payload.lines) || [],
      tradeable: (payload && payload.tradeable) || [],
    };
    tradeDrafts = new Map();
    renderTrade();
  } catch (e) {
    handleApiError(e, 'Réseau indisponible');
    $('#trade-body').innerHTML = '<p class="empty">Réseau indisponible.</p>';
  }
}

function renderTrade() {
  const open = tradeState.lines.filter((l) => l.open);
  const blockaded = open.filter((l) => l.blockaded).length;

  $('#trade-headline').textContent =
    `${open.length} ligne${open.length > 1 ? 's' : ''} ouverte${open.length > 1 ? 's' : ''}`
    + (blockaded ? ` · ${blockaded} sous blocus` : '');

  $('#trade-body').innerHTML =
    renderTradeAlarm() + renderTradeOpener() + renderTradeLines(open);

  bindTrade();
}

/* Les mondes coupes, en tete et avant tout le reste. Muet quand tout va bien :
   une alarme qui se declenche a chaque ouverture est une alarme qu'on apprend
   a ignorer. */
function renderTradeAlarm() {
  const cut = (state.myTerritories || []).filter(
    (t) => t.holding && t.holding.owned && (t.holding.deactivated || !t.holding.connected)
  );
  if (!cut.length) return '';

  const rows = cut
    .map(
      (t) => `<div class="trade-alarm__row">
        <b>${esc(territoryLabel(t))}</b>
        <span>${esc(tradeFate(t.holding))}</span>
      </div>`
    )
    .join('');

  return `<div class="trade-alarm">
    <span class="ov">Coupés du réseau</span>${rows}
  </div>`;
}

function tradeFate(h) {
  if (!h.deactivated) return `aucune route — stabilité ${h.stability}`;
  return `éteint — ${secessionIn(h).toLowerCase().replace(/\.$/, '')}`;
}

/* Ouvrir une route. L'arrivee ne propose que des mondes de la MEME galaxie que
   le depart, et ecarte ce qui est deja relie : laisser le choix pour le
   reprendre par un refus serait offrir une impasse. */
function renderTradeOpener() {
  const worlds = state.myTerritories || [];
  if (worlds.length < 2) {
    return '<p class="mod-intro">Il faut tenir deux mondes pour ouvrir une ligne.</p>';
  }

  const options = worlds
    .map((t) => `<option value="${esc(t.id)}">${esc(territoryLabel(t))}</option>`)
    .join('');

  return `<div class="trade-open">
    <span class="ov">Ouvrir une ligne</span>
    <div class="field">
      <label for="trade-from">De</label>
      <select id="trade-from">${options}</select>
    </div>
    <div class="field">
      <label for="trade-to">Vers</label>
      <select id="trade-to"></select>
    </div>
    <div class="trade-open__acts">
      <button class="btn btn--sm btn--pri" id="trade-go">Ouvrir la ligne</button>
    </div>
    <p class="mod-intro">Un cargo doit être en orbite du monde d'<b>arrivée</b> :
      c'est le convoi qui vient de faire le voyage, et il est consommé en
      établissant la route. Les deux bouts ont besoin d'un dépôt, et c'est le
      plus faible des deux qui fixe le débit.</p>
  </div>`;
}

/* Les arrivees possibles pour un depart donne. */
function tradeDestinations(originId, open) {
  const worlds = state.myTerritories || [];
  const origin = worlds.find((t) => t.id === originId);
  if (!origin) return [];

  return worlds.filter((t) => {
    if (t.id === origin.id) return false;
    if (galaxyOf(t) !== galaxyOf(origin)) return false;
    return !open.some(
      (l) =>
        (l.origin_id === origin.id && l.destination_id === t.id)
        || (l.origin_id === t.id && l.destination_id === origin.id)
    );
  });
}

function renderTradeLines(open) {
  if (!open.length) {
    return `<p class="empty">Aucune ligne ouverte. Deux mondes d'un même système
      se nourrissent sans rien construire ; ailleurs, il faut une route.</p>`;
  }
  return open.map(renderTradeLine).join('');
}

function renderTradeLine(line) {
  const draft = draftFor(line);
  const declared = draft.reduce((sum, f) => sum + (Number(f.rate) || 0), 0);
  const over = line.throughput > 0 && declared > line.throughput;

  const flows = draft
    .map(
      (f, i) => `<div class="trade-flow">
      <span class="trade-flow__name">${esc(resourceLabel(f.resource))}</span>
      <button class="btn btn--sm" data-flow-way="${esc(line.id)}" data-index="${i}"
        title="${esc(flowWay(line, f))}">${f.to_origin ? '←' : '→'}</button>
      <input class="qty" type="number" min="0" step="1" value="${esc(Math.round(f.rate))}"
        data-flow-rate="${esc(line.id)}" data-index="${i}"
        aria-label="Débit ${esc(resourceLabel(f.resource))}">
      <span class="trade-flow__unit">/h</span>
      <button class="btn btn--sm btn--ghost" data-flow-drop="${esc(line.id)}"
        data-index="${i}" title="Ne plus envoyer">✕</button>
    </div>`
    )
    .join('');

  const left = tradeState.tradeable.filter((k) => !draft.some((f) => f.resource === k));

  return `<div class="trade-line">
    <div class="trade-line__head">
      <b>${esc(tradeEnd(line, false))} → ${esc(tradeEnd(line, true))}</b>
      ${
        line.blockaded
          ? `<span class="trade-chip trade-chip--bad" title="${esc(BLOCKADE_HINT)}">SOUS BLOCUS</span>`
          : ''
      }
      <span class="trade-line__rate">${esc(fmtNumber(Math.round(line.throughput)))}/h</span>
    </div>
    <div class="trade-flows">${flows}</div>
    ${
      left.length
        ? `<div class="trade-adder">
      <select data-flow-add="${esc(line.id)}">
        ${left.map((k) => `<option value="${esc(k)}">${esc(resourceLabel(k))}</option>`).join('')}
      </select>
      <button class="btn btn--sm" data-flow-add-go="${esc(line.id)}">Ajouter</button>
    </div>`
        : ''
    }
    <div class="bar"><i style="width:${Math.min(
      100,
      line.throughput > 0 ? (declared / line.throughput) * 100 : 0
    )}%"></i></div>
    <p class="trade-load${over ? ' trade-load--over' : ''}">
      ${esc(fmtNumber(Math.round(declared)))} déclarés sur ${esc(
        fmtNumber(Math.round(line.throughput))
      )}/h${over ? ' — les derniers ne partiront pas' : ''}
    </p>
    <div class="trade-line__acts">
      <button class="btn btn--sm btn--pri" data-flow-apply="${esc(line.id)}">Appliquer</button>
      <button class="btn btn--sm btn--dgr" data-line-close="${esc(line.id)}"
        title="Le cargo qui l'a ouverte ne revient pas : il s'était consommé sur la route.">Démonter</button>
    </div>
  </div>`;
}

/* Le nom d'un bout de ligne, quoi qu'il arrive.

   Le serveur recopie le nom du monde, et ce nom vient du client de jeu qui a
   bâti le système : un monde jamais nommé en a un vide, et la ligne
   s'afficherait comme une flèche entre deux riens. */
function tradeEnd(line, destination) {
  const given = destination ? line.destination : line.origin;
  if (given) return given;

  const id = destination ? line.destination_id : line.origin_id;
  const known = (state.myTerritories || []).find((t) => t.id === id);
  return known ? territoryLabel(known) : `Monde ${id}`;
}

function flowWay(line, flow) {
  return flow.to_origin
    ? `${tradeEnd(line, true)} → ${tradeEnd(line, false)}`
    : `${tradeEnd(line, false)} → ${tradeEnd(line, true)}`;
}

function resourceLabel(key) {
  const meta = RESOURCE_BY_KEY[key];
  return (meta && meta.label) || humanize(key);
}

function draftFor(line) {
  if (!tradeDrafts.has(line.id)) {
    /* Recopie : éditer la réponse du serveur en place ferait d'une saisie
       abandonnée un état qu'on croit enregistré. */
    tradeDrafts.set(
      line.id,
      (line.flows || []).map((f) => ({
        resource: f.resource,
        rate: Number(f.rate) || 0,
        to_origin: !!f.to_origin,
      }))
    );
  }
  return tradeDrafts.get(line.id);
}

function bindTrade() {
  const open = tradeState.lines.filter((l) => l.open);
  const from = $('#trade-from');
  const to = $('#trade-to');

  if (from && to) {
    const fill = () => {
      const list = tradeDestinations(Number(from.value), open);
      to.innerHTML = list
        .map((t) => `<option value="${esc(t.id)}">${esc(territoryLabel(t))}</option>`)
        .join('');
      const go = $('#trade-go');
      if (go) go.disabled = !list.length;
    };
    from.addEventListener('change', fill);
    fill();

    const go = $('#trade-go');
    if (go) {
      go.addEventListener('click', () => openTradeLine(Number(from.value), Number(to.value)));
    }
  }

  const body = $('#trade-body');

  body.querySelectorAll('[data-flow-way]').forEach((el) => {
    el.addEventListener('click', () => {
      const flow = draftById(Number(el.dataset.flowWay))[Number(el.dataset.index)];
      if (!flow) return;
      flow.to_origin = !flow.to_origin;
      renderTrade();
    });
  });

  body.querySelectorAll('[data-flow-rate]').forEach((el) => {
    el.addEventListener('change', () => {
      const flow = draftById(Number(el.dataset.flowRate))[Number(el.dataset.index)];
      if (!flow) return;
      flow.rate = Math.max(0, Number(el.value) || 0);
      renderTrade();
    });
  });

  body.querySelectorAll('[data-flow-drop]').forEach((el) => {
    el.addEventListener('click', () => {
      draftById(Number(el.dataset.flowDrop)).splice(Number(el.dataset.index), 1);
      renderTrade();
    });
  });

  body.querySelectorAll('[data-flow-add-go]').forEach((el) => {
    el.addEventListener('click', () => {
      const id = Number(el.dataset.flowAddGo);
      const picker = body.querySelector(`[data-flow-add="${CSS.escape(String(id))}"]`);
      if (!picker || !picker.value) return;
      draftById(id).push({ resource: picker.value, rate: 0, to_origin: false });
      renderTrade();
    });
  });

  body.querySelectorAll('[data-flow-apply]').forEach((el) => {
    el.addEventListener('click', () => applyFlows(Number(el.dataset.flowApply)));
  });

  body.querySelectorAll('[data-line-close]').forEach((el) => {
    el.addEventListener('click', () => demountTradeLine(Number(el.dataset.lineClose)));
  });
}

function draftById(id) {
  const line = tradeState.lines.find((l) => l.id === id);
  return line ? draftFor(line) : [];
}

async function openTradeLine(originId, destinationId) {
  try {
    await api.openTradeLine(originId, destinationId);
    toast('Ligne ouverte.', 'info', 'Commerce');
    await loadTrade();
  } catch (e) {
    /* Le refus vient du serveur : dépôt manquant, cargo absent, deux galaxies
       différentes. La console ne saurait pas le formuler, et surtout elle ne
       saurait pas rester d'accord avec lui. */
    handleApiError(e, 'Ligne refusée');
  }
}

async function applyFlows(id) {
  try {
    await api.setTradeFlows(id, draftById(id));
    toast('Flux déclarés.', 'info', 'Commerce');
    await loadTrade();
  } catch (e) {
    handleApiError(e, 'Flux refusés');
  }
}

async function demountTradeLine(id) {
  try {
    await api.closeTradeLine(id);
    toast('Ligne démontée.', 'info', 'Commerce');
    await loadTrade();
  } catch (e) {
    handleApiError(e, 'Démontage refusé');
  }
}

async function openDevices() {
  $('#modal-devices').classList.remove('hidden');
  $('#devices-list').innerHTML = '<p class="empty">Lecture…</p>';
  await loadDevices();
}

function closeDevices() {
  $('#modal-devices').classList.add('hidden');
}

function devicesOpen() {
  return !$('#modal-devices').classList.contains('hidden');
}

async function loadDevices() {
  try {
    renderDevices(await api.devices());
  } catch (e) {
    $('#devices-list').innerHTML = `<p class="empty">${esc(
      e instanceof ApiError ? e.message : 'Lecture impossible'
    )}</p>`;
  }
}

function renderDevices(devices) {
  const list = $('#devices-list');

  if (!devices.length) {
    list.innerHTML = `<p class="empty">Aucun appareil enregistré. Cochez « rester
      connecté » dans le client de jeu pour ne plus saisir votre mot de passe.</p>`;
    $('#devices-revoke-all').classList.add('hidden');
    return;
  }

  $('#devices-revoke-all').classList.remove('hidden');
  list.innerHTML = devices
    .map(
      (d) => `<div class="device-row">
        <span class="device-row__id">
          <span class="device-row__name">${esc(d.label || 'Appareil sans nom')}</span>
          <span class="device-row__when">${esc(describeDevice(d))}</span>
        </span>
        <button class="btn btn--sm btn--dgr" data-device="${d.id}">Déconnecter</button>
      </div>`
    )
    .join('');
}

/* Ce qu'on dit d'un appareil : quand il a servi, et jusqu'à quand il ouvre
   encore. Sa date de création n'apprend rien — c'est le dernier usage qui dit
   si l'on reconnaît la machine. */
function describeDevice(device) {
  const used = parseUtc(device.last_used_at || device.created_at);
  const until = parseUtc(device.expires_at);
  const parts = [];
  if (used) parts.push(`vu le ${used.toLocaleDateString('fr-FR')}`);
  if (until) parts.push(`expire le ${until.toLocaleDateString('fr-FR')}`);
  return parts.join(' · ');
}

async function revokeDevice(id) {
  try {
    await api.revokeDevice(id);
    toast('Appareil déconnecté.', 'ok', 'Compte');
    await loadDevices();
  } catch (e) {
    handleApiError(e, 'Compte');
  }
}

async function revokeAllDevices() {
  /* Y compris la clé de la machine d'où part la demande : c'est dit avant, pas
     après. La session de cette console, elle, reste ouverte — elle ne tient pas
     à une clé d'appareil. */
  if (!window.confirm('Déconnecter tous les appareils, y compris celui-ci ?')) return;

  try {
    const done = await api.revokeDevices();
    toast(`${(done && done.revoked) || 0} appareil(s) déconnecté(s).`, 'ok', 'Compte');
    await loadDevices();
  } catch (e) {
    handleApiError(e, 'Compte');
  }
}

/* Le choix d'un territoire est au-dessus d'un territoire : l'adresse remonte à
   la galaxie, sans quoi un rechargement rouvrirait le monde qu'on vient de
   quitter. Partagé par les deux scènes. */
function showWorldPicker() {
  stopTimers();
  stopMapTimers();
  state.territoryId = null;
  syncUrl();
  renderPicker();
  showView('pick');
}

function runChromeAction(name) {
  switch (name) {
    case 'map':
      openGalaxyMap();
      break;
    case 'worlds':
      showWorldPicker();
      break;
    case 'refresh-territory':
      reloadTerritory(true);
      break;
    case 'refresh-map':
      loadGalaxyMap();
      break;
    case 'research':
      openResearch();
      break;
    case 'refresh-research':
      loadResearch();
      break;
    case 'moderation':
      openModeration();
      break;
    case 'admin':
      openAdmin();
      break;
    case 'settings':
      openSettings();
      break;
    case 'settings-close':
      closeSettings();
      break;
    case 'devices':
      openDevices();
      break;
    case 'devices-close':
      closeDevices();
      break;
    case 'claim-close':
      closeClaim();
      break;
    case 'trade':
      openTrade();
      break;
    case 'trade-close':
      closeTrade();
      break;
    case 'logout':
      logout();
      break;
    default:
      break;
  }
}

function initChrome() {
  paintChrome();

  /* Nommé plutôt que `data-act` : il demande confirmation, et une action qui
     ouvre une question n'a pas sa place dans la table des gestes immédiats. */
  $('#devices-revoke-all').addEventListener('click', revokeAllDevices);

  document.addEventListener('click', (ev) => {
    const toggle = ev.target.closest('[data-menu-toggle]');
    if (toggle) {
      const pop = toggle.closest('[data-menu]').querySelector('[data-menu-pop]');
      const opening = pop.hidden;
      closeMenus();
      pop.hidden = !opening;
      toggle.setAttribute('aria-expanded', String(opening));
      return;
    }

    /* Cliquer ailleurs referme : c'est ce qu'on tente d'instinct pour sortir
       d'un menu, et sans reponse il donne l'impression d'etre coince. */
    if (!ev.target.closest('[data-menu-pop]')) closeMenus();

    /* Le bouton « Déconnecter » d'une ligne porte l'appareil visé : la liste se
       redessine à chaque lecture, et un branchement par bouton se perdrait à la
       première. */
    const device = ev.target.closest('[data-device]');
    if (device) {
      revokeDevice(Number(device.dataset.device));
      return;
    }

    /* Le fond assombri de la fenetre sert de zone de fermeture. */
    if (ev.target.id === 'modal-settings') {
      closeSettings();
      return;
    }

    if (ev.target.id === 'modal-devices') {
      closeDevices();
      return;
    }

    const action = ev.target.closest('[data-act]');
    if (!action) return;
    closeMenus();
    runChromeAction(action.dataset.act);
  });

  /* Échap ferme ce qui est ouvert, du plus superficiel au plus profond : la
     fenêtre, puis le menu. Ce qui reste — la sélection sur la carte — est géré
     par la carte elle-même. */
  window.addEventListener(
    'keydown',
    (ev) => {
      if (ev.key !== 'Escape') return;
      if (devicesOpen()) {
        closeDevices();
        ev.stopImmediatePropagation();
        return;
      }
      if (settingsOpen()) {
        closeSettings();
        ev.stopImmediatePropagation();
        return;
      }
      if (menusOpen()) {
        closeMenus();
        ev.stopImmediatePropagation();
      }
    },
    true
  );
}

/* ============================================================
   carte de la galaxie

   Ce que les listes ne savent pas dire : où sont les choses les unes par
   rapport aux autres. On y lit ce qu'on possède, jamais si deux mondes sont
   voisins — et c'est pourtant la seule question qui compte pour déplacer une
   flotte, puisqu'elle ne voyage que par les liaisons entre étoiles.

   Le réseau vient du serveur. La règle de voisinage vit dans le modèle et dans
   le client de jeu ; la console n'en a aucune copie, et une carte qui
   réinventerait ses propres liaisons montrerait un réseau que les flottes
   n'empruntent pas.

   En SVG et non en canvas : les étoiles sont alors des éléments, donc
   survolables, cliquables et titrables sans écrire un moteur de désignation.
   Elles se comptent en centaines, le DOM tient largement.
   ============================================================ */

/* Repère de tracé, en unités de vue. Le `viewBox` fait la mise à l'échelle
   jusqu'aux pixels, ce qui laisse écrire des rayons et des tailles de texte
   dans un ordre de grandeur lisible — projeter directement en coordonnées de
   galaxie donnerait des polices de cent unités de haut. */
const MAP_W = 1000;
const MAP_H = 625;
const MAP_PAD = 42;

const MAP_STAR_R = 3.4;
const MAP_STAR_MINE_R = 5.2;
const MAP_FLEET_R = 7;

/* Écart entre une étoile et les flottes qui y stationnent. Assez pour ne pas
   la recouvrir : c'est elle qu'on vise quand on veut envoyer la flotte
   ailleurs. */
const MAP_FLEET_ORBIT = 14;

/* Bornes du zoom, en multiples du cadrage d'origine. Assez pour separer deux
   etoiles d'un amas serre, pas au point de perdre la galaxie de vue. */
const MAP_ZOOM_MIN = 0.9;
const MAP_ZOOM_MAX = 14;
const MAP_ZOOM_STEP = 1.25;

/* Au-dela, les etoiles sont assez espacees pour porter toutes leur nom. En
   deca, seuls les mondes du joueur sont nommes : trois cents libelles
   superposes ne se lisent pas. */
const MAP_LABEL_ZOOM = 2.4;

let mapTimer = null;
let mapLoading = false;

/* Facteur d'agrandissement courant. Les rayons et les tailles de texte sont
   ecrits pour un cadrage d'origine et divises par lui : sans cela, zoomer
   grossirait les etoiles au lieu de les ecarter, ce qui n'apprend rien. */
function mapZoom() {
  const view = state.map.view;
  return view && view.w > 0 ? MAP_W / view.w : 1;
}

/* Les flottes bougent : leur position se recalcule sur l'horloge locale à
   partir de `travel.legs`, exactement comme le fait le client de jeu. Le
   serveur donne un reste, jamais une heure d'arrivée — les deux pendules n'ont
   aucune raison d'être d'accord. */
function mapFleetsReadNow(fleets) {
  state.map.fleets = Array.isArray(fleets) ? fleets : [];
  state.map.readAt = Date.now();
}

function mapSecondsLeft(fleet) {
  if (!fleet.travel) return 0;
  const elapsed = (Date.now() - state.map.readAt) / 1000;
  return Math.max(0, (fleet.travel.seconds_left || 0) - elapsed);
}

/* Le saut en cours et la fraction parcourue.

   On remonte depuis la fin : ce que le serveur donne est un reste, et le
   convertir en écoulé demanderait une somme que le reste rend inutile. */
function mapLeg(fleet) {
  const t = fleet.travel;
  if (!t || !Array.isArray(t.legs) || !t.legs.length) return null;
  if (!Array.isArray(t.route) || t.route.length < 2) return null;

  const left = mapSecondsLeft(fleet);
  let behind = 0;
  let leg = 0;
  for (let i = t.legs.length - 1; i >= 0; i--) {
    leg = i;
    if (left <= behind + t.legs[i]) break;
    behind += t.legs[i];
  }

  const span = t.legs[leg];
  const progress = span > 0 ? Math.min(1, Math.max(0, (span - (left - behind)) / span)) : 1;
  return { leg: Math.min(leg, t.route.length - 2), progress };
}

/* ---------- projection ---------- */

/* La galaxie est un disque dans le plan XZ : la hauteur ne sépare rien et
   n'est pas projetée.

   La même échelle sur les deux axes, jamais un étirement pour remplir le
   cadre : c'est la distance qui fait la durée d'un saut, et une carte étirée
   mentirait sur les deux. */
function buildMapProjection(systems) {
  const points = systems.map((s) => s.position).filter(Boolean);
  if (!points.length) return null;

  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  points.forEach((p) => {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minZ = Math.min(minZ, p.z);
    maxZ = Math.max(maxZ, p.z);
  });

  const spanX = Math.max(1e-6, maxX - minX);
  const spanZ = Math.max(1e-6, maxZ - minZ);
  const scale = Math.min((MAP_W - 2 * MAP_PAD) / spanX, (MAP_H - 2 * MAP_PAD) / spanZ);

  return {
    scale,
    offX: (MAP_W - spanX * scale) / 2 - minX * scale,
    offZ: (MAP_H - spanZ * scale) / 2 - minZ * scale,
  };
}

function mapProject(position) {
  const p = state.map.projection;
  if (!p || !position) return null;
  return { x: position.x * p.scale + p.offX, y: position.z * p.scale + p.offZ };
}

function mapSystem(id) {
  return state.map.byId.get(id) || null;
}

function mapStarPoint(id) {
  const system = mapSystem(id);
  return system ? mapProject(system.position) : null;
}

/* Où se trouve une flotte : sur sa liaison quand elle vole, en couronne autour
   de son étoile quand elle stationne. */
function mapFleetPoint(fleet) {
  if (fleet.travel) {
    const step = mapLeg(fleet);
    if (step) {
      const a = mapStarPoint(fleet.travel.route[step.leg]);
      const b = mapStarPoint(fleet.travel.route[step.leg + 1]);
      if (a && b) {
        return {
          x: a.x + (b.x - a.x) * step.progress,
          y: a.y + (b.y - a.y) * step.progress,
        };
      }
    }
  }

  const anchor = mapStarPoint(fleet.system_id);
  if (!anchor) return null;

  const rank = state.map.rank.get(fleet.id) || { index: 0, total: 1 };
  const angle = (-90 + (rank.total > 1 ? (rank.index * 360) / rank.total : 0)) * (Math.PI / 180);
  /* L'ecart suit le zoom : une couronne en unites de carte se refermerait sur
     l'etoile en zoomant, alors que c'est justement la qu'on veut les separer. */
  const orbit = MAP_FLEET_ORBIT / mapZoom();
  return {
    x: anchor.x + Math.cos(angle) * orbit,
    y: anchor.y + Math.sin(angle) * orbit,
  };
}

/* Le rang d'une flotte dans la couronne dépend des autres, ce qu'aucune ne
   sait d'elle-même. Recalculé à chaque lecture, et pour les seules flottes à
   l'arrêt : celles en vol se placent sur leur liaison, où rien ne les
   superpose. */
function rankMapFleets() {
  const perStar = new Map();
  state.map.fleets.forEach((f) => {
    if (f.travel) return;
    perStar.set(f.system_id, (perStar.get(f.system_id) || 0) + 1);
  });

  const seen = new Map();
  state.map.rank = new Map();
  state.map.fleets.forEach((f) => {
    if (f.travel) return;
    const index = seen.get(f.system_id) || 0;
    seen.set(f.system_id, index + 1);
    state.map.rank.set(f.id, { index, total: perStar.get(f.system_id) || 1 });
  });
}

/* ---------- chargement ---------- */

async function openGalaxyMap({ push = true } = {}) {
  if (!state.galaxy) {
    toast('Choisissez une galaxie.', 'err', 'Carte');
    return;
  }

  /* La carte est la galaxie entiere, pas un monde : l'adresse s'arrete au nom
     de la galaxie. */
  state.territoryId = null;
  syncUrl({ replace: !push });

  showView('galaxy');
  $('#map-galaxy').textContent = state.galaxy;
  $('#map-frame').innerHTML = '<p class="empty">Chargement…</p>';

  await loadGalaxyMap();
  startMapTimers();
}

async function loadGalaxyMap() {
  if (mapLoading) return;
  mapLoading = true;

  try {
    /* Les systèmes et les liaisons ne bougent pas d'une lecture à l'autre : on
       ne les redemande que si la galaxie a changé. Les flottes, si. */
    const needsTopology = state.map.galaxy !== state.galaxy || !state.map.systems.length;

    const [systems, lanes, fleets] = await Promise.all([
      needsTopology ? api.galaxySystems(state.galaxy).catch(() => []) : Promise.resolve(state.map.systems),
      needsTopology ? api.galaxyLanes(state.galaxy).catch(() => []) : Promise.resolve(state.map.lanes),
      api.galaxyFleets(state.galaxy).catch(() => []),
    ]);

    if (needsTopology) {
      state.map.galaxy = state.galaxy;
      state.map.systems = Array.isArray(systems) ? systems : [];
      state.map.lanes = Array.isArray(lanes) ? lanes : [];
      state.map.byId = new Map(state.map.systems.map((s) => [s.id, s]));
      state.map.projection = buildMapProjection(state.map.systems);
      state.map.view = { x: 0, y: 0, w: MAP_W, h: MAP_H };
      state.map.selectedSystem = null;
      state.map.selectedFleet = null;
    }

    mapFleetsReadNow(fleets);
    rankMapFleets();

    /* Les territoires du joueur disent quelles étoiles sont à lui. Ils sont
       déjà en mémoire pour le sélecteur de territoire ; les relire ici les
       garde justes après une colonisation. */
    state.myTerritories = await api.myTerritories(state.galaxy).catch(() => state.myTerritories);
  } finally {
    mapLoading = false;
  }

  renderMap();
  renderMapSummary();
  renderMapSelection();
  $('#map-updated').textContent = `à jour · ${new Date().toLocaleTimeString('fr-FR')}`;
}

/* Seules les flottes sont relues : la topologie d'une galaxie ne change pas en
   cours de partie. */
async function refreshMapFleets() {
  if (!state.galaxy || mapLoading) return;
  try {
    const fleets = await api.galaxyFleets(state.galaxy);
    mapFleetsReadNow(fleets);
    rankMapFleets();
    renderMapFleets();
    renderMapSummary();
    renderMapSelection();
  } catch (e) {
    /* Une lecture ratée laisse la carte telle quelle : elle vieillit, elle ne
       disparaît pas. */
  }
}

function startMapTimers() {
  stopMapTimers();
  /* Le déplacement se calcule ici : une seconde suffit pour un trajet qui se
     compte en minutes, et rien ne justifie d'animer image par image. */
  mapTimer = setInterval(() => {
    renderMapFleets();
    if (state.map.tick++ % 15 === 0) refreshMapFleets();
  }, 1000);
}

function stopMapTimers() {
  if (mapTimer) clearInterval(mapTimer);
  mapTimer = null;
}

/* ---------- rendu ---------- */

function mySystemIds() {
  const ids = new Set();
  state.myTerritories.forEach((t) => {
    if (t.system && t.system.id) ids.add(t.system.id);
  });
  return ids;
}

function systemLabel(system) {
  return system.name || `Système ${system.id}`;
}

function renderMap() {
  const frame = $('#map-frame');

  if (!state.map.systems.length || !state.map.projection) {
    frame.innerHTML = `<p class="empty">Aucun système enregistré dans
      ${esc(state.galaxy || 'cette galaxie')}. Une galaxie générée hors du serveur
      n'a pas de carte à montrer.</p>`;
    return;
  }

  const mine = mySystemIds();
  const k = 1 / mapZoom();
  const named = mapZoom() >= MAP_LABEL_ZOOM;

  const lanes = state.map.lanes
    .map((lane) => {
      const a = mapStarPoint(lane.from);
      const b = mapStarPoint(lane.to);
      if (!a || !b) return '';
      return `<line class="map-lane" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}"
        x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"></line>`;
    })
    .join('');

  const stars = state.map.systems
    .map((system) => {
      const point = mapProject(system.position);
      if (!point) return '';
      const owned = mine.has(system.id);
      const on = state.map.selectedSystem === system.id;
      const radius = (owned ? MAP_STAR_MINE_R : MAP_STAR_R) * k;
      const label = owned || named
        ? `<text class="map-label" x="${point.x.toFixed(1)}"
             y="${(point.y + radius + 9 * k).toFixed(1)}"
             style="font-size:${(8 * k).toFixed(2)}px">${esc(systemLabel(system))}</text>`
        : '';
      return `<circle class="map-star${owned ? ' map-star--mine' : ''}${on ? ' map-star--on' : ''}"
          data-system="${system.id}" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}"
          r="${radius.toFixed(2)}"><title>${esc(systemLabel(system))} — ${esc(String(system.territories_count || 0))} territoire(s)</title></circle>${label}`;
    })
    .join('');

  const view = state.map.view || { x: 0, y: 0, w: MAP_W, h: MAP_H };
  frame.innerHTML = `<svg viewBox="${view.x.toFixed(2)} ${view.y.toFixed(2)} ${view.w.toFixed(2)} ${view.h.toFixed(2)}" preserveAspectRatio="xMidYMid meet"
      role="img" aria-label="Carte de la galaxie ${esc(state.galaxy || '')}">
    <g>${lanes}</g>
    <g id="map-route-layer"></g>
    <g id="map-halo-layer"></g>
    <g>${stars}</g>
    <g id="map-fleet-layer"></g>
  </svg>`;

  renderMapFleets();
  paintMapSelection();
}

/* Rafraichit les marques de designation sans refaire la carte.

   Refaire tout etait la cause de deux ennuis : le double-clic ne se formait
   jamais, le premier clic ayant remplace l'etoile que le second allait
   frapper ; et le survol se perdait a chaque changement. Ce sont des classes a
   basculer, pas une carte a repeindre. */
function paintMapSelection() {
  const svg = mapSvg();
  if (!svg) return;

  svg.querySelectorAll('[data-system]').forEach((node) => {
    node.classList.toggle(
      'map-star--on', Number(node.getAttribute('data-system')) === state.map.selectedSystem);
  });

  svg.querySelectorAll('[data-fleet]').forEach((node) => {
    node.classList.toggle(
      'map-fleet--on', Number(node.getAttribute('data-fleet')) === state.map.selectedFleet);
  });

  /* L'anneau vit dans sa propre couche : il change de place a chaque
     designation, alors que les etoiles, elles, ne bougent pas. */
  const halos = document.getElementById('map-halo-layer');
  if (halos) {
    const system = state.map.selectedSystem ? mapSystem(state.map.selectedSystem) : null;
    const point = system ? mapProject(system.position) : null;
    if (!point) {
      halos.innerHTML = '';
    } else {
      const k = 1 / mapZoom();
      const radius =
        (mySystemIds().has(system.id) ? MAP_STAR_MINE_R : MAP_STAR_R) * k + 5 * k;
      halos.innerHTML = `<circle class="map-halo" cx="${point.x.toFixed(1)}"
        cy="${point.y.toFixed(1)}" r="${radius.toFixed(2)}"></circle>`;
    }
  }

  renderMapRoute();
}

const SVG_NS = 'http://www.w3.org/2000/svg';

/* Le nœud d'une flotte, cree une seule fois puis reutilise.

   C'est la correction d'un defaut qui rendait les flottes a peu pres
   inselectionnables : la couche etait refaite par `innerHTML` chaque seconde,
   et un clic dont l'enfoncement et le relachement encadraient un
   rafraichissement voyait son element disparaitre entre les deux. Le navigateur
   remonte alors au premier ancetre commun — le cadre — et la flotte n'etait
   jamais reconnue. Une chance sur quelques-unes a chaque essai, ce qui se vit
   comme « ca ne marche pas ».

   Les nœuds survivent donc, et seule leur position change. C'est aussi moins de
   travail : deplacer un attribut plutot que reconstruire l'arbre. */
function mapFleetNode(layer, fleetId) {
  const existing = layer.querySelector(`[data-fleet="${fleetId}"]`);
  if (existing) return existing;

  const node = document.createElementNS(SVG_NS, 'g');
  node.setAttribute('data-fleet', String(fleetId));

  const body = document.createElementNS(SVG_NS, 'circle');
  body.setAttribute('class', 'map-fleet__body');
  node.appendChild(body);

  const count = document.createElementNS(SVG_NS, 'text');
  count.setAttribute('class', 'map-fleet__count');
  node.appendChild(count);

  node.appendChild(document.createElementNS(SVG_NS, 'title'));

  layer.appendChild(node);
  return node;
}

/* Appele chaque seconde : on ne touche qu'aux attributs qui bougent. */
function renderMapFleets() {
  const layer = document.getElementById('map-fleet-layer');
  if (!layer) return;

  const k = 1 / mapZoom();
  const alive = new Set();

  state.map.fleets.forEach((fleet) => {
    const point = mapFleetPoint(fleet);
    if (!point) return;

    alive.add(String(fleet.id));
    const node = mapFleetNode(layer, fleet.id);

    node.setAttribute('class', 'map-fleet'
      + (state.map.selectedFleet === fleet.id ? ' map-fleet--on' : '')
      + (fleet.size ? '' : ' map-fleet--idle'));
    node.setAttribute(
      'transform', `translate(${point.x.toFixed(1)},${point.y.toFixed(1)})`);

    node.querySelector('.map-fleet__body').setAttribute('r', (MAP_FLEET_R * k).toFixed(2));

    const count = node.querySelector('.map-fleet__count');
    count.setAttribute('style', `font-size:${(9 * k).toFixed(2)}px`);
    count.textContent = String(fleet.size || 0);

    node.querySelector('title').textContent =
      `${fleetName(fleet)} — ${mapFleetState(fleet)}`;
  });

  /* Ce que le serveur ne rend plus : une flotte dissoute, ou fondue dans une
     autre. */
  Array.from(layer.children).forEach((node) => {
    if (!alive.has(node.getAttribute('data-fleet'))) node.remove();
  });

  renderMapRoute();
}

/* La route de la seule flotte désignée : toutes les routes tracées en
   permanence feraient une toile par-dessus une carte qui porte déjà son
   réseau. */
function renderMapRoute() {
  const layer = document.getElementById('map-route-layer');
  if (!layer) return;

  const fleet = selectedMapFleet();
  const step = fleet && fleet.travel ? mapLeg(fleet) : null;
  if (!fleet || !step) {
    layer.innerHTML = '';
    return;
  }

  const points = [mapFleetPoint(fleet)];
  for (let i = step.leg + 1; i < fleet.travel.route.length; i++) {
    points.push(mapStarPoint(fleet.travel.route[i]));
  }

  const usable = points.filter(Boolean);
  if (usable.length < 2) {
    layer.innerHTML = '';
    return;
  }

  layer.innerHTML = `<polyline class="map-lane map-lane--route" fill="none"
    points="${usable.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')}"></polyline>`;
}

function renderMapSummary() {
  const mine = mySystemIds();
  const ships = state.map.fleets.reduce((sum, f) => sum + (f.size || 0), 0);
  const moving = state.map.fleets.filter((f) => f.travel).length;

  const chip = (key, value, title) =>
    `<div class="chip" title="${esc(title)}">
      <span class="k">${esc(key)}</span><span class="v">${esc(value)}</span>
    </div>`;

  $('#map-summary').innerHTML = [
    chip('SYS', fmtNumber(state.map.systems.length), 'Systèmes de la galaxie'),
    chip('MOI', fmtNumber(mine.size), 'Systèmes où vous tenez un territoire'),
    chip('FLT', fmtNumber(state.map.fleets.length), 'Vos flottes'),
    chip('VSX', fmtNumber(ships), 'Vaisseaux, toutes flottes confondues'),
    chip('RTE', fmtNumber(moving), 'Flottes en route'),
  ].join('');

  $('#map-title').textContent = state.galaxy || '—';
  $('#map-legend').innerHTML =
    `<span class="map-legend-key"><i style="background:var(--acc)"></i>vos systèmes</span>`
    + `<span class="map-legend-key"><i style="background:var(--fg-off)"></i>autres</span>`
    + `<span class="map-legend-key">les traits sont les liaisons qu'empruntent les flottes</span>`;
}

/* ---------- sélection ---------- */

function selectedMapFleet() {
  return state.map.fleets.find((f) => f.id === state.map.selectedFleet) || null;
}

function fleetName(fleet) {
  return fleet.name || `Flotte ${fleet.id}`;
}

function mapFleetState(fleet) {
  if (fleet.travel) {
    const target = mapSystem(fleet.travel.destination_id);
    return `en route vers ${target ? systemLabel(target) : `le système ${fleet.travel.destination_id}`}`
      + ` · arrivée dans ${fmtDuration(mapSecondsLeft(fleet))}`;
  }
  if (fleet.orbiting_territory_id) return 'en orbite';
  return 'à l’arrêt';
}

function selectMapFleet(id) {
  state.map.selectedFleet = state.map.selectedFleet === id ? null : id;
  paintMapSelection();
  renderMapSelection();
}

function selectMapSystem(id) {
  state.map.selectedSystem = id;
  paintMapSelection();
  renderMapSelection();
}

function renderMapSelection() {
  const host = $('#map-sel-body');
  const fleet = selectedMapFleet();
  const system = state.map.selectedSystem ? mapSystem(state.map.selectedSystem) : null;

  if (!fleet && !system) {
    $('#map-sel-title').textContent = '—';
    host.innerHTML = `<p class="empty">Choisissez une étoile ou une flotte.
      Une flotte désignée peut ensuite être envoyée vers l'étoile que vous
      choisirez.</p>`;
    return;
  }

  $('#map-sel-title').textContent = fleet ? fleetName(fleet) : systemLabel(system);
  host.innerHTML = (fleet ? fleetBlock(fleet) : '') + (system ? systemBlock(system, fleet) : '');
}

function fleetBlock(fleet) {
  const composition = Object.entries(fleet.composition || {});
  const ships = composition.length
    ? composition
        .map(([type, n]) => `<span class="cost">${esc(humanize(type))} <b>×${esc(fmtNumber(n))}</b></span>`)
        .join('')
    : '<span class="cost">Flotte vide.</span>';

  const route = fleet.travel
    ? `<p class="map-route">Route ${esc(
        (fleet.travel.route || []).map((id) => {
          const s = mapSystem(id);
          return s ? systemLabel(s) : id;
        }).join(' → ')
      )}</p>`
    : '';

  return `<div class="row">
    <div class="ico">${icon('fleet')}</div>
    <div class="row-main">
      <div class="row-head">
        <span class="row-name">${esc(fleetName(fleet))}</span>
        <span class="lvl">${esc(fmtNumber(fleet.size || 0))} vaisseau(x)</span>
      </div>
      <div class="costs"><span class="cost">${esc(mapFleetState(fleet))}</span></div>
      <div class="costs">${ships}</div>
      ${route}
      <div class="map-actions">
        ${fleet.travel
          ? `<button class="btn btn--sm" data-map-stop="${fleet.id}">Interrompre</button>`
          : ''}
        <button class="btn btn--sm btn--ghost" data-map-deselect="1">Désélectionner</button>
      </div>
    </div>
  </div>`;
}

function systemBlock(system, fleet) {
  const here = state.myTerritories.filter((t) => t.system && t.system.id === system.id);
  const fleets = state.map.fleets.filter((f) => !f.travel && f.system_id === system.id);

  const territories = here.length
    ? here
        .map(
          (t) => `<div class="row-head">
            <span class="row-name">${esc(territoryLabel(t))}</span>
            <button class="btn btn--sm" data-map-territory="${t.id}">Administrer</button>
          </div>`
        )
        .join('')
    : '<p class="desc">Vous ne tenez aucun territoire dans ce système.</p>';

  const present = fleets.length
    ? fleets
        .map(
          (f) => `<div class="row-head">
            <span class="row-name">${esc(fleetName(f))}</span>
            <span class="lvl">${esc(fmtNumber(f.size || 0))}</span>
            <button class="btn btn--sm btn--ghost" data-map-fleet="${f.id}">Désigner</button>
          </div>`
        )
        .join('')
    : '';

  /* L'ordre de route n'apparaît que s'il a un sens : une flotte désignée, et
     une destination qui n'est pas déjà la sienne. */
  const canSend = fleet && fleet.system_id !== system.id;

  return `<div class="row">
    <div class="row-main">
      <div class="row-head">
        <span class="row-name">${esc(systemLabel(system))}</span>
        <span class="lvl">${esc(fmtNumber(system.territories_count || 0))} territoire(s)</span>
      </div>
      ${territories}
      ${present}
      <div class="map-actions">
        ${canSend
          ? `<button class="btn btn--sm btn--pri" data-map-send="${system.id}">
               Envoyer ${esc(fleetName(fleet))} ici
             </button>`
          : ''}
      </div>
    </div>
  </div>`;
}

/* ---------- ordres ---------- */

async function sendMapFleet(systemId) {
  const fleet = selectedMapFleet();
  if (!fleet) return;

  try {
    const updated = await api.travelFleet(fleet.id, systemId);
    toast(
      `${fleetName(fleet)} en route · arrivée dans ${fmtDuration(
        updated && updated.travel ? updated.travel.seconds_left : 0
      )}.`,
      'info',
      'Flottes'
    );
  } catch (e) {
    /* 409 : aucune suite de liaisons ne mène là. Deux amas assez serrés pour
       se suffire ne se relient jamais, et c'est au joueur qu'il faut le dire. */
    handleApiError(e, 'Ordre refusé');
    return;
  }

  await refreshMapFleets();
}

async function stopMapFleet(fleetId) {
  try {
    await api.stopFleetTravel(fleetId);
    toast('Voyage interrompu.', 'info', 'Flottes');
  } catch (e) {
    handleApiError(e, 'Ordre refusé');
    return;
  }
  await refreshMapFleets();
}

/* ---------- déplacement et zoom ----------

   Le cadrage est le `viewBox` du SVG : déplacer et zoomer se ramènent à le
   bouger et à le retailler, sans toucher à un seul point du tracé. Une galaxie
   de trois cents étoiles se manipule alors sans rien recalculer.

   Le déplacement écrit l'attribut directement, sans repeindre : glisser doit
   suivre la souris à l'image près, et refaire quelques centaines de nœuds à
   chaque mouvement se verrait. Le zoom, lui, repeint — c'est le seul geste qui
   change la taille apparente des étoiles, donc les rayons compensés. */

function mapSvg() {
  const frame = $('#map-frame');
  return frame ? frame.querySelector('svg') : null;
}

function applyMapView() {
  const svg = mapSvg();
  const view = state.map.view;
  if (!svg || !view) return;
  svg.setAttribute(
    'viewBox',
    `${view.x.toFixed(2)} ${view.y.toFixed(2)} ${view.w.toFixed(2)} ${view.h.toFixed(2)}`
  );
}

/* Le point de la carte sous le pointeur.

   `preserveAspectRatio="xMidYMid meet"` centre le contenu et le met à l'échelle
   uniformément : la boîte réellement peinte est plus petite que le cadre sur un
   des deux axes, et il faut retrouver ce décalage avant de convertir. Le
   négliger fait dériver le zoom d'autant. */
function mapPointerPoint(ev) {
  const svg = mapSvg();
  const view = state.map.view;
  if (!svg || !view) return null;

  const rect = svg.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return null;

  const scale = Math.min(rect.width / view.w, rect.height / view.h);
  const originX = rect.left + (rect.width - view.w * scale) / 2;
  const originY = rect.top + (rect.height - view.h * scale) / 2;

  return {
    x: view.x + (ev.clientX - originX) / scale,
    y: view.y + (ev.clientY - originY) / scale,
    scale,
  };
}

/* Zoome autour d'un point, qui reste sous le pointeur.

   Zoomer sur le centre du cadre obligerait à repositionner la vue après chaque
   cran : ce qu'on veut regarder est sous la souris, pas au milieu. */
function zoomMapAround(point, factor) {
  const view = state.map.view;
  if (!view) return;

  const zoom = mapZoom();
  const wanted = Math.min(MAP_ZOOM_MAX, Math.max(MAP_ZOOM_MIN, zoom * factor));
  if (Math.abs(wanted - zoom) < 1e-6) return;

  const w = MAP_W / wanted;
  const h = MAP_H / wanted;

  /* Le point garde sa place relative dans le cadre. */
  const ratioX = view.w > 0 ? (point.x - view.x) / view.w : 0.5;
  const ratioY = view.h > 0 ? (point.y - view.y) / view.h : 0.5;

  state.map.view = { x: point.x - ratioX * w, y: point.y - ratioY * h, w, h };
  renderMap();
}

function zoomMapCentre(factor) {
  const view = state.map.view;
  if (!view) return;
  zoomMapAround({ x: view.x + view.w / 2, y: view.y + view.h / 2 }, factor);
}

function fitMap() {
  state.map.view = { x: 0, y: 0, w: MAP_W, h: MAP_H };
  renderMap();
}

function initMapNavigation() {
  const frame = $('#map-frame');
  if (!frame) return;

  $('#map-zoom-in').addEventListener('click', () => zoomMapCentre(MAP_ZOOM_STEP));
  $('#map-zoom-out').addEventListener('click', () => zoomMapCentre(1 / MAP_ZOOM_STEP));
  $('#map-fit').addEventListener('click', fitMap);

  /* `passive: false` : sans cela le navigateur refuse l'annulation et la page
     défile pendant qu'on zoome. */
  frame.addEventListener(
    'wheel',
    (ev) => {
      if (!state.map.view) return;
      ev.preventDefault();
      const point = mapPointerPoint(ev);
      if (!point) return;
      zoomMapAround(point, ev.deltaY < 0 ? MAP_ZOOM_STEP : 1 / MAP_ZOOM_STEP);
    },
    { passive: false }
  );

  let drag = null;

  frame.addEventListener('pointerdown', (ev) => {
    if (!state.map.view || ev.button !== 0) return;
    const point = mapPointerPoint(ev);
    if (!point) return;

    drag = {
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
      viewX: state.map.view.x,
      viewY: state.map.view.y,
      scale: point.scale,
    };
    state.map.dragged = false;
    /* Pas de capture ici.

       `setPointerCapture` reoriente vers l'element capturant non seulement les
       evenements de pointeur mais aussi les `click` et `dblclick` qui suivent :
       la cible devenait le cadre, et `closest('[data-system]')` ne trouvait
       plus rien. Un simple clic ne devait donc jamais capturer — on ne prend le
       pointeur qu'au moment ou un vrai glissement commence. */
  });

  frame.addEventListener('pointermove', (ev) => {
    if (!drag || ev.pointerId !== drag.pointerId) return;

    const dx = ev.clientX - drag.startX;
    const dy = ev.clientY - drag.startY;

    /* En deçà, c'est un clic dont la main a tremblé : le traiter comme un
       déplacement empêcherait de désigner quoi que ce soit. */
    if (!state.map.dragged && Math.abs(dx) + Math.abs(dy) < 4) return;

    if (!state.map.dragged) {
      /* Le glissement commence pour de bon : maintenant on peut capturer, la
         souris pouvant sortir du cadre en cours de route. */
      state.map.dragged = true;
      frame.classList.add('map-frame--panning');
      try {
        frame.setPointerCapture(ev.pointerId);
        drag.captured = true;
      } catch (e) {
        /* capture refusee : le glissement marche tant que le pointeur reste
           dans le cadre, ce qui est le cas courant */
      }
    }

    state.map.view.x = drag.viewX - dx / drag.scale;
    state.map.view.y = drag.viewY - dy / drag.scale;
    applyMapView();
  });

  const endDrag = (ev) => {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    if (drag.captured) {
      try {
        frame.releasePointerCapture(ev.pointerId);
      } catch (e) {
        /* le pointeur a pu être perdu en route */
      }
    }
    drag = null;
    frame.classList.remove('map-frame--panning');
  };

  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);

  /* Double-clic sur un de ses mondes : on l'administre. Le geste le plus court
     vers ce qu'on vient de trouver sur la carte. */
  frame.addEventListener('dblclick', (ev) => {
    const starEl = ev.target.closest('[data-system]');
    if (!starEl) return;

    const systemId = Number(starEl.dataset.system);
    const here = state.myTerritories.filter((t) => t.system && t.system.id === systemId);

    if (!here.length) {
      /* Ne rien faire du tout laisserait croire que le double-clic est casse,
         alors qu'il n'y a simplement rien a administrer ici. */
      const system = mapSystem(systemId);
      toast(
        `Vous ne tenez aucun territoire dans ${system ? systemLabel(system) : 'ce système'}.`,
        'info',
        'Carte'
      );
      return;
    }

    stopMapTimers();
    selectTerritory(here[0].id);
  });
}

/* ---------- branchements ---------- */

function initGalaxyMap() {
  /* Enveloppe : branchee directement, elle recevrait l'evenement de clic en
     guise d'options. Les commandes de la barre du haut passent, elles, par
     `data-act`. */
  $('#pick-map').addEventListener('click', () => openGalaxyMap());

  /* Echap : lache la selection sans quitter la carte. La barre du haut ecoute
     la meme touche en phase de capture et arrete l'evenement quand elle a une
     fenetre ou un menu a fermer — ce qui est ouvert par-dessus se ferme
     d'abord. */
  window.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    if ($('#view-galaxy').classList.contains('hidden')) return;
    if (state.map.selectedFleet === null && state.map.selectedSystem === null) return;
    state.map.selectedFleet = null;
    state.map.selectedSystem = null;
    paintMapSelection();
    renderMapSelection();
  });

  initMapNavigation();

  $('#map-frame').addEventListener('click', (ev) => {
    /* Un deplacement se termine par un clic : le laisser designer ce qui se
       trouve sous le pointeur a l'arrivee changerait la selection a chaque
       fois qu'on bouge la carte. */
    if (state.map.dragged) {
      state.map.dragged = false;
      return;
    }

    const fleetEl = ev.target.closest('[data-fleet]');
    if (fleetEl) {
      selectMapFleet(Number(fleetEl.dataset.fleet));
      return;
    }

    const starEl = ev.target.closest('[data-system]');
    if (starEl) {
      selectMapSystem(Number(starEl.dataset.system));
      return;
    }

    /* Le vide : on lache la selection. C'est le geste qu'on tente d'instinct
       pour sortir d'une selection, et sans reponse il donne l'impression que
       la carte est bloquee. */
    if (state.map.selectedSystem !== null || state.map.selectedFleet !== null) {
      state.map.selectedSystem = null;
      state.map.selectedFleet = null;
      paintMapSelection();
      renderMapSelection();
    }
  });

  $('#map-sel-body').addEventListener('click', (ev) => {
    const send = ev.target.closest('[data-map-send]');
    if (send) {
      sendMapFleet(Number(send.dataset.mapSend));
      return;
    }
    const stop = ev.target.closest('[data-map-stop]');
    if (stop) {
      stopMapFleet(Number(stop.dataset.mapStop));
      return;
    }
    const pick = ev.target.closest('[data-map-fleet]');
    if (pick) {
      selectMapFleet(Number(pick.dataset.mapFleet));
      return;
    }
    const deselect = ev.target.closest('[data-map-deselect]');
    if (deselect) {
      state.map.selectedFleet = null;
      paintMapSelection();
      renderMapSelection();
      return;
    }
    const territory = ev.target.closest('[data-map-territory]');
    if (territory) {
      stopMapTimers();
      selectTerritory(Number(territory.dataset.mapTerritory));
    }
  });
}

/* ============================================================
   démarrage
   ============================================================ */

async function enterGame() {
  /* Les roles ne viennent pas de `api.login`, qui serialise sans droits : seul
     `/api/auth/me` les porte. Sans cette relecture, l'entree d'administration
     resterait cachee a un administrateur qui vient de se connecter. */
  try {
    state.user = (await api.me()) || state.user;
  } catch (e) {
    /* Session ouverte mais lecture refusee : on garde ce qu'on a. */
  }
  applyAdminAccess();

  // Le droit de moderer se porte sur une galaxie : il se relit a chaque
  // entree, pas une fois pour la session.
  const [territories, catalog] = await Promise.all([
    api.myTerritories(state.galaxy).catch(() => []),
    api.catalog().catch(() => ({ ships: [], defenses: [] })),
    refreshModeration(),
  ]);
  state.myTerritories = territories;
  state.catalog = catalog || { ships: [], defenses: [] };

  await applyRoute({ push: false });
}

/* Amene la vue a ce que dit l'adresse.

   La carte est la vue d'accueil : c'est la seule qui montre la partie entiere,
   et le choix d'un monde vient apres. On y retombe donc chaque fois que
   l'adresse ne designe pas un monde precis.

   `push: false` quand c'est l'adresse qui commande la vue et non l'inverse —
   au demarrage, et sur un retour arriere : y repondre en empilant une entree
   rendrait le bouton retour inutilisable. */
async function applyRoute({ push = false } = {}) {
  const route = readRoute();

  /* Un retour arriere peut traverser les galaxies : les possessions changent
     avec elles, et rien de la precedente ne doit rester a l'ecran. */
  if (route.galaxy && route.galaxy !== state.galaxy) {
    state.galaxy = route.galaxy;
    state.territory = null;
    state.territoryId = null;
    fillGalaxySelect($('#login-galaxy'));
    fillGalaxySelect($('#pick-galaxy'));
    state.myTerritories = await api.myTerritories(state.galaxy).catch(() => []);
    await refreshModeration();
  }

  if (!state.galaxy) {
    renderPicker();
    showView('pick');
    return;
  }

  if (route.research) {
    await openResearch({ push });
    return;
  }

  const wanted = route.territoryId;
  if (wanted && state.myTerritories.some((t) => t.id === wanted)) {
    await selectTerritory(wanted, { push });
    return;
  }

  if (wanted) {
    /* Adresse pointant un monde qui n'est pas au joueur, ou plus : on le dit
       et on retombe sur la carte, plutot que d'ouvrir une scene vide. */
    toast(
      `Le territoire ${wanted} ne vous appartient pas dans ${state.galaxy}.`,
      'err',
      'Adresse'
    );
  }

  await openGalaxyMap({ push });
}

async function boot() {
  initTheme();
  initLogin();
  initAdmin();
  initEvents();
  initChrome();
  initModeration();
  initGalaxyMap();
  initResearch();

  // Routes publiques : la liste des galaxies, qui permet de choisir la sienne
  // sur l'ecran de login, et ce que le serveur annonce a qui n'a pas encore de
  // compte.
  await Promise.all([loadGalaxies(), loadServerNotice()]);

  try {
    state.user = await api.me();
    await enterGame();
  } catch (e) {
    showView('login');
  }
}

boot();
