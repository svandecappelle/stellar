/* ============================================================
   systemview.js — la regle de la descente, en dehors du dessin.

   La carte de la galaxie montrait des etoiles et rien de ce qu'elles
   abritent : pour voir un systeme il fallait quitter la carte. Ce module tient
   ce qu'il faut pour le faire POUSSER SUR PLACE quand on s'approche — ou se
   posent ses mondes, a partir de quel agrandissement ils apparaissent, et ce
   que la galaxie doit ceder pour qu'on les lise.

   Pur, sans DOM et sans etat : c'est ici que se decide ce qui, rate, ne se voit
   qu'en jouant — un systeme qui deborde sur son voisin, des anneaux qui
   surgissent d'un coup, un monde pose a un rang qui n'est pas le sien. Le
   client de jeu a paye trois sessions pour apprendre que ces regles-la ne
   doivent pas vivre au milieu d'un rendu.

   TOUT EST UNE FONCTION DE L'AGRANDISSEMENT, jamais un declenchement. Un etat
   declenche se rate quand l'agrandissement saute — une molette qui devale, un
   bouton qui recadre — et l'on se retrouve avec des anneaux sans systeme, ou un
   systeme sans anneaux. Un etat recalcule rattrape toujours.

   L'AGRANDISSEMENT N'EST PAS UNE LONGUEUR. Les seuils ci-dessous sont des
   FRACTIONS DE LA LARGEUR DE LA VUE, et c'est ce qui les rend transposables :
   un systeme se deplie quand il occupe assez d'ecran pour etre lu, quelle que
   soit la galaxie, le nombre d'etoiles ou leur ecartement. Un seuil ecrit en
   unites de carte serait juste sur la galaxie qui l'a vu naitre, et faux sur
   toutes les autres — sans que rien ne le dise.
   ============================================================ */

/* ---------- ou se pose un monde ----------

   La meme regle que le client de jeu (`SystemOrbits`), au meme endroit dans la
   chaine : le serveur ne stocke PAS les orbites. Il donne un rang, et c'est le
   client qui en tire une distance. Une copie de la formule serait juste
   jusqu'au premier equilibrage, puis fausse en silence. */

/** Rayon du premier anneau, en unites de systeme. */
export const ORBIT_FIRST = 1600;

/** Ce que vaut un rang orbital de plus. */
export const ORBIT_STEP = 400;

/** Rayon nominal du rang donne. */
export function nominalRadius(rank) {
  return ORBIT_FIRST + Math.max(0, Number(rank) || 0) * ORBIT_STEP;
}

/* L'angle d'or : la suite la plus reguliere qu'on puisse tirer d'un compteur,
   et celle qui evite le mieux les alignements. */
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

/** Un angle stable pour un monde dont on ne connait pas la place. */
export function inventedAngle(seed) {
  const n = Math.abs(Math.round(Number(seed) || 0));
  return (n * GOLDEN) % (Math.PI * 2);
}

/* Ou est ce monde dans son systeme : sa position enregistree si le serveur en
   tient une, son rang sinon.

   `placed` dit lequel des deux a repondu, et ce n'est pas de la comptabilite :
   **l'angle d'un monde non place est une invention.** Stable — meme monde,
   meme place a chaque lecture — mais elle ne dit rien du jeu, et personne ne
   doit lire une conjonction sur cette carte. Le RAYON, lui, est juste dans les
   deux cas. */
export function orbitOf(territory) {
  if (!territory) return { radius: 0, angle: 0, placed: false };

  const p = territory.characteristics && territory.characteristics.position;
  if (p) {
    const x = Number(p.x) || 0;
    const z = Number(p.z) || 0;
    const flat = Math.hypot(x, z);
    if (flat > 0) return { radius: flat, angle: Math.atan2(z, x), placed: true };
  }

  return {
    radius: nominalRadius(territory.position),
    angle: inventedAngle(territory.id || territory.position || 1),
    placed: false,
  };
}

/* Le rayon du systeme entier : celui de son monde le plus lointain.

   Zero quand il n'y a rien a mesurer. L'appelant doit alors s'abstenir plutot
   que d'inventer une taille — un systeme dessine a une taille devinee se
   reorganiserait a l'arrivee des vraies donnees, exactement la ou le joueur
   regarde. */
export function outerRadius(territories) {
  return (territories || []).reduce(
    (outer, t) => Math.max(outer, orbitOf(t).radius), 0);
}

/* Le plan du systeme, en unites de CARTE, relativement a son etoile.

   `drawn` est la place qu'on lui laisse ; les unites de systeme s'annulent dans
   le rapport. Meme mecanique que le client de jeu, ou l'echelle du systeme est
   deduite de la place disponible et non d'une constante : deux systemes visites
   de suite doivent se ressembler, alors que leurs mondes ne se ressemblent pas.

   Rendu trie du plus proche au plus lointain : les anneaux se peignent dans cet
   ordre, et une planete interieure doit passer par-dessus l'anneau exterieur,
   jamais dessous. */
export function layout(territories, drawn) {
  const list = (territories || []).filter(Boolean);
  const outer = outerRadius(list);
  if (!list.length || !(drawn > 0) || !(outer > 0)) return [];

  const k = drawn / outer;
  return list
    .map((t) => {
      const o = orbitOf(t);
      const ring = o.radius * k;
      return {
        id: t.id,
        position: Number(t.position) || 1,
        placed: o.placed,
        ring,
        x: Math.cos(o.angle) * ring,
        y: Math.sin(o.angle) * ring,
      };
    })
    .sort((a, b) => a.ring - b.ring);
}

/* ---------- quelle place laisser a un systeme ---------- */

/* Un systeme deplie ne doit jamais toucher son voisin : deux couronnes qui se
   chevauchent ne se lisent plus comme deux systemes, mais comme une toile. On
   le taille donc sur l'ECARTEMENT REEL des etoiles de cette galaxie-ci, et non
   sur une constante — une galaxie serree et une galaxie lache n'ont pas la
   meme place a donner. */
export const SPACING_SHARE = 0.34;
export const RADIUS_MIN = 1.5;
export const RADIUS_MAX = 14;

/** L'ecartement typique de ces points : la mediane des plus proches voisins.
 *
 *  La mediane et non la moyenne : le coeur d'une galaxie est bien plus dense
 *  que ses bras, et une moyenne tiree vers le haut par quelques etoiles isolees
 *  donnerait des systemes qui se recouvrent la ou il y a foule. */
export function nearestSpacing(points) {
  const list = (points || []).filter((p) => p && isFinite(p.x) && isFinite(p.y));
  if (list.length < 2) return 0;

  const nearest = list
    .map((a) => {
      let best = Infinity;
      list.forEach((b) => {
        if (a === b) return;
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d > 0 && d < best) best = d;
      });
      return best;
    })
    .filter((d) => isFinite(d))
    .sort((a, b) => a - b);

  if (!nearest.length) return 0;
  return nearest[Math.floor(nearest.length / 2)];
}

/** Le rayon qu'un systeme occupe sur la carte, en unites de carte. */
export function systemRadius(spacing) {
  if (!(spacing > 0)) return RADIUS_MIN;
  return Math.min(RADIUS_MAX, Math.max(RADIUS_MIN, spacing * SPACING_SHARE));
}

/* ---------- a partir de quand on voit le systeme ---------- */

/* En fractions du PETIT COTE de la vue. Ces trois nombres disent « assez gros
   pour qu'on devine », « assez gros pour qu'on lise », « assez gros, n'allons
   pas plus loin », et ils valent pour toutes les galaxies. Les convertir en
   agrandissements demande le rayon dessine, qui, lui, depend de la galaxie.

   LE PETIT COTE, ET C'EST TOUT LE PIEGE. Une fraction d'ecran doit dire de
   QUELLE dimension elle est la fraction, sans quoi elle est juste sur l'une et
   fausse sur l'autre. Un systeme est rond : c'est le cote le plus court qui le
   coupe. Cale sur la largeur d'un cadre en 16/10, il occupait les quatre
   cinquiemes de celle-ci — donc une fois et quart la hauteur, et ses deux
   anneaux exterieurs sortaient du cadre par le haut et par le bas. Ce qu'on
   voit alors n'est pas un systeme qui deborde : ce sont des mondes qui
   manquent. */
export const SHARE_OPEN = 0.16;
export const SHARE_FULL = 0.54;
export const SHARE_DEEPEST = 0.80;

/* Les trois agrandissements qui en decoulent.
 *
 *  `viewSpan` est le PETIT COTE du cadrage d'origine, en unites de carte.
 *
 *  `deepest` est le FOND DE LA DESCENTE, et il est derive comme les deux
 *  autres. Un plancher constant laisserait les galaxies denses inatteignables
 *  et les galaxies laches au ras de l'etoile : c'est la faute que le client de
 *  jeu a payee, un plancher calcule sur un systeme moyen et la camera dedans
 *  pour tous les plus petits. */
export function reach(drawnRadius, viewSpan) {
  const at = (share) => (share * viewSpan) / (2 * Math.max(1e-6, drawnRadius));
  return { open: at(SHARE_OPEN), full: at(SHARE_FULL), deepest: at(SHARE_DEEPEST) };
}

/* Ce qui est deplie, de 0 a 1.

   Adouci aux deux bouts : une rampe droite fait apparaitre les anneaux d'un
   coup a l'instant du seuil, et l'oeil lit ce saut comme un defaut de rendu
   plutot que comme une arrivee. */
export function unfold(zoom, bounds) {
  if (!bounds || !(bounds.full > bounds.open)) return 0;
  const t = (zoom - bounds.open) / (bounds.full - bounds.open);
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
}

/* Ce qui arrive et ce qui s'en va sont LE MEME NOMBRE, lu dans les deux sens.

   Deux rampes reglees separement rouvrent le defaut au premier ajustement :
   soit on efface la galaxie alors qu'on la regarde encore, soit on peint un
   systeme par-dessus un reseau de liaisons qui n'a pas fini de partir.

   Et le fond ne descend pas a zero : rien n'occulte rien sur une carte a plat,
   et les liaisons restantes disent ou l'on se trouve dans la galaxie. Ce serait
   le contraire dans une scene en volume, ou la geometrie de la carte finit par
   contenir le systeme entier. */
export const GALAXY_FLOOR = 0.16;

export function galaxyDim(reveal) {
  const r = Math.min(1, Math.max(0, Number(reveal) || 0));
  return 1 - (1 - GALAXY_FLOOR) * r;
}

/* ---------- quel systeme se deplie ---------- */

/* Un seul a la fois : chacun coute une lecture au serveur, et vingt systemes
   deplies dans la meme vue ne se liraient pas mieux qu'un champ d'etoiles.

   Celui qu'on designe l'emporte, le plus proche du centre sinon. Zoomer a la
   molette garde le point sous le pointeur immobile pendant que tout le reste
   s'ecarte : l'etoile visee devient donc naturellement la plus proche du
   centre, sans qu'il faille la recadrer de force. */

/* L'autre doit etre nettement plus proche pour prendre la place. Sans cette
   marge, deux etoiles a egale distance du centre se volent le systeme a chaque
   image, et l'on voit deux couronnes clignoter l'une contre l'autre. */
export const FOCUS_KEEP = 0.75;

/** Jusqu'ou chercher, en multiples de la plus grande dimension du cadre. */
export const FOCUS_REACH = 0.6;

export function focusStar(view, stars, { current = null, selected = null } = {}) {
  if (!view || !(view.w > 0) || !Array.isArray(stars) || !stars.length) return null;

  const cx = view.x + view.w / 2;
  const cy = view.y + view.h / 2;
  /* Au-dela, l'etoile n'est plus a l'ecran : deplier son systeme peindrait des
     anneaux dont on ne verrait que le bord. */
  const limit = Math.max(view.w, view.h) * FOCUS_REACH;

  let best = null;
  let bestAt = Infinity;
  let keptAt = null;
  let pickedAt = null;

  stars.forEach((s) => {
    if (!s || !isFinite(s.x) || !isFinite(s.y)) return;
    const d = Math.hypot(s.x - cx, s.y - cy);
    if (d > limit) return;
    if (s.id === current) keptAt = d;
    if (s.id === selected) pickedAt = d;
    if (d < bestAt) {
      bestAt = d;
      best = s.id;
    }
  });

  if (pickedAt !== null) return selected;
  if (keptAt !== null && keptAt * FOCUS_KEEP <= bestAt) return current;
  return best;
}
