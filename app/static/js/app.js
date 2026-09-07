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
let reloading = false;
/* Événements dont on a déjà constaté la fin : le serveur les archive au
   prochain /update, mais tant qu'ils reviennent on ne relance qu'une fois. */
let settledEvents = new Set();

/* ============================================================
   utilitaires
   ============================================================ */

const $ = (sel) => document.querySelector(sel);

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
  };
}

function routePath(galaxy, territoryId) {
  if (!galaxy) return '/';
  const base = `/galaxy/${encodeURIComponent(galaxy)}`;
  return territoryId ? `${base}/territory/${territoryId}` : base;
}

/* Ecrit l'adresse de la vue courante.

   `replace` quand la vue n'est pas un pas de navigation — une correction de
   l'adresse, ou le premier affichage : empiler une entree la ferait apparaitre
   dans l'historique comme un endroit ou revenir. */
function syncUrl({ replace = false } = {}) {
  const path = routePath(state.galaxy, state.territoryId);
  try {
    if (path === window.location.pathname && !window.location.search) return;
    const entry = { galaxy: state.galaxy, territoryId: state.territoryId };
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
  const wanted = readRoute().galaxy || state.galaxy;
  state.galaxy =
    (wanted && state.galaxies.includes(wanted) && wanted) || state.galaxies[0] || wanted || null;

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
  ['login', 'pick', 'command', 'moderation', 'galaxy'].forEach((v) => {
    $(`#view-${v}`).classList.toggle('hidden', v !== name);
  });
  if (name !== 'command') stopTimers();
  if (name !== 'galaxy') stopMapTimers();
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

function initLogin() {
  $('#login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('#login-submit');
    const err = $('#login-error');
    err.classList.add('hidden');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    try {
      const chosen = $('#login-galaxy').value;
      if (chosen) {
        state.galaxy = chosen;
      }
      state.user = await api.login($('#login-user').value.trim(), $('#login-pass').value);
      $('#login-pass').value = '';
      await enterGame();
    } catch (e) {
      err.textContent = e instanceof ApiError ? e.message : 'Connexion impossible';
      err.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Se connecter';
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
  renderResources();
  renderRail();
  renderTabs();
  renderTabBody();
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
    (r) => !r.material || yields[r.key] > 0 || (res[r.key] || 0) > 0
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
      const cls = ev ? 'row busy' : affordable ? 'row' : 'row off';

      return `<div class="${cls}">
      <div class="ico">${icon(name)}</div>
      <div class="row-main">
        <div class="row-head">
          <span class="row-name">${esc(humanize(name))}</span>
          <span class="lvl">LVL ${esc(b.level)}</span>
          <button class="btn btn--sm${affordable && !ev ? ' btn--pri' : ''}"
            data-build-building="${esc(name)}" ${ev || !affordable ? 'disabled' : ''}>
            ${ev ? 'En cours' : 'Upgrade'}
          </button>
        </div>
        <div class="costs">
          ${costMarkup(costs, resources)}
          ${gainMarkup(gains)}
          <span class="cost">Durée <b>${esc(fmtDuration(b.duration))}</b></span>
        </div>
        <p class="desc">${esc(BUILDING_DESC[name] || 'Structure planétaire.')}</p>
        ${progressMarkup(ev, `Niveau ${Number(b.level) + 1} en construction`)}
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
    if (orb.dataset.owned !== '1') {
      toast("Ce territoire n'est pas sous votre contrôle.", 'err', 'Orbite');
      return;
    }
    const id = Number(orb.dataset.orbit);
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
  worlds: 'worlds',
  'refresh-territory': 'refresh',
  'refresh-map': 'refresh',
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
    case 'moderation':
      openModeration();
      break;
    case 'settings':
      openSettings();
      break;
    case 'settings-close':
      closeSettings();
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

    /* Le fond assombri de la fenetre sert de zone de fermeture. */
    if (ev.target.id === 'modal-settings') {
      closeSettings();
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
  initEvents();
  initChrome();
  initModeration();
  initGalaxyMap();

  // Route publique : la liste des galaxies s'obtient avant toute connexion,
  // ce qui permet de choisir la sienne sur l'ecran de login.
  await loadGalaxies();

  try {
    state.user = await api.me();
    await enterGame();
  } catch (e) {
    showView('login');
  }
}

boot();
