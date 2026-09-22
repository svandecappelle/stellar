# -*- coding: utf-8 -*-

"""
La regle de la descente, cote console : `app/static/js/systemview.js`.

Ce module decide ou se posent les mondes d'un systeme sur la carte de la
galaxie, a partir de quel agrandissement ils apparaissent, et ce que la carte
cede pour qu'on les lise. Rien de tout cela ne se voit dans une suite d'API :
une valeur fausse ici ne casse rien -- elle donne un systeme qui deborde sur son
voisin, des anneaux qui surgissent d'un coup, ou une descente qu'on ne peut pas
finir. Autant de defauts qui ne se constatent qu'en jouant, et qu'on cherche
alors du cote du rendu.

D'ou ces epingles. Elles portent sur les INVARIANTS, pas sur des nombres
d'agrement :

  * les orbites suivent la meme formule que le client de jeu (`SystemOrbits`).
    Le serveur ne stocke pas les orbites : il donne un rang, et les deux clients
    en tirent une distance. Deux formules finiraient par dessiner deux
    systemes ;
  * un systeme deplie tient dans la place que lui laisse son voisin le plus
    proche ;
  * le depliage est CONTINU et MONOTONE. Un saut se lit comme un defaut de
    rendu, et un seuil unique rendrait le retour impossible ;
  * ce qui arrive et ce qui s'en va sont le meme nombre lu dans les deux sens ;
  * la designation du systeme deplie ne clignote pas entre deux etoiles a egale
    distance.

Le module est du JavaScript de navigateur : il s'eprouve avec `node`, qui est
present sur les executeurs comme sur les postes. Sans lui, le test est saute
plutot qu'echoue -- une suite Python n'a pas a exiger une chaine JavaScript.

Les fichiers sont copies en `.mjs` dans un dossier temporaire : le depot n'a pas
de `package.json`, et node lit un `.js` comme un module CommonJS. Copier plutot
qu'en poser un dans `app/static` -- ce dossier est servi aux navigateurs, et il
n'a pas a porter la configuration d'un outil de test.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, '..', '..', 'app', 'static', 'js', 'systemview.js')

#: Ce que la carte mesure, en unites de carte. Lus ici parce que le test les
#: EPROUVE : un controle qui recopierait ses propres seuils ne prouverait que
#: sa propre coherence.
MAP_W = 1000
MAP_H = 625

PROBE = r"""
import * as m from './systemview.mjs';

const out = {};
const near = (a, b) => Math.abs(a - b) < 1e-6;

/* --- les orbites, telles que le client de jeu les pose --- */
out.orbits = [0, 1, 2, 5].map((r) => m.nominalRadius(r));

/* Une position enregistree l'emporte sur le rang : c'est elle qui fait foi. */
const placed = m.orbitOf({ id: 1, position: 1, characteristics: { position: { x: 3000, y: 0, z: 0 } } });
out.placed = { radius: placed.radius, placed: placed.placed };
const ranked = m.orbitOf({ id: 1, position: 1, characteristics: {} });
out.ranked = { radius: ranked.radius, placed: ranked.placed };

/* --- la place d'un systeme --- */
out.spacing = m.nearestSpacing([
  { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 10 }, { x: 10, y: 10 },
]);
out.radiusOfTen = m.systemRadius(10);
out.radiusOfNothing = m.systemRadius(0);
out.radiusOfHuge = m.systemRadius(1e6);

/* --- le plan, en unites de carte --- */
const worlds = [1, 2, 4].map((p, i) => ({ id: i + 1, position: p, characteristics: {} }));
const plan = m.layout(worlds, 8);
out.plan = plan.map((p) => ({
  id: p.id, ring: p.ring, radial: Math.hypot(p.x, p.y),
}));
out.planSorted = plan.every((p, i) => i === 0 || plan[i - 1].ring <= p.ring);
out.planOfNothing = m.layout([], 8).length;
out.planWithoutRoom = m.layout(worlds, 0).length;

/* --- la descente --- */
const bounds = m.reach(8, 625);
out.bounds = bounds;
out.unfoldBelow = m.unfold(bounds.open - 1, bounds);
out.unfoldAt = m.unfold(bounds.open, bounds);
out.unfoldAbove = m.unfold(bounds.full + 10, bounds);

let last = -1;
let monotone = true;
let biggestStep = 0;
for (let z = 0; z <= bounds.deepest * 1.2; z += bounds.deepest / 500) {
  const v = m.unfold(z, bounds);
  if (v < last - 1e-9) monotone = false;
  if (last >= 0) biggestStep = Math.max(biggestStep, Math.abs(v - last));
  last = v;
}
out.monotone = monotone;
out.biggestStep = biggestStep;

/* Ce qui arrive et ce qui s'en va : un seul nombre, lu dans les deux sens. */
out.dimPairs = [0, 0.25, 0.5, 0.75, 1].map((r) => [r, m.galaxyDim(r)]);
out.dimClamped = [m.galaxyDim(-3), m.galaxyDim(12)];

/* --- quel systeme se deplie --- */
const view = { x: 0, y: 0, w: 100, h: 62.5 };
/* Deux etoiles presque a egale distance du centre (2 et 2.4), et une hors du
   cadre. C'est le cas qui fait clignoter : l'ecart entre les deux premieres est
   de l'ordre du tremblement de la main. */
const stars = [
  { id: 1, x: 52, y: 31.25 },
  { id: 2, x: 47.6, y: 31.25 },
  { id: 9, x: 4000, y: 4000 },
];
out.nearest = m.focusStar(view, stars, {});
out.kept = m.focusStar(view, stars, { current: 2 });
out.picked = m.focusStar(view, stars, { current: 2, selected: 1 });
out.farSelectionIgnored = m.focusStar(view, stars, { selected: 9 });
out.outOfReach = m.focusStar(view, [{ id: 9, x: 4000, y: 4000 }], {});
out.noStars = m.focusStar(view, [], {});

/* Une etoile nettement plus proche prend la place de celle qu'on tenait. */
out.stolen = m.focusStar(view, [{ id: 1, x: 50, y: 31 }, { id: 2, x: 90, y: 31 }], { current: 2 });

console.log(JSON.stringify(out));
"""


@pytest.fixture(name='rules', scope='module')
def rules():
    """Ce que le module repond, lu une fois pour tout le fichier."""
    if shutil.which('node') is None:
        pytest.skip("node absent : la regle de la descente n'est pas eprouvee ici")

    workdir = tempfile.mkdtemp(prefix='stellar-systemview-')
    try:
        shutil.copyfile(MODULE, os.path.join(workdir, 'systemview.mjs'))
        with open(os.path.join(workdir, 'probe.mjs'), 'w', encoding='utf-8') as handle:
            handle.write(PROBE)

        run = subprocess.run(
            ['node', 'probe.mjs'], cwd=workdir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert run.returncode == 0, run.stderr.decode('utf-8', 'replace')
        return json.loads(run.stdout.decode('utf-8'))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_orbites_suivent_la_formule_du_client(rules):
    """
    1600 + rang x 400, exactement comme `SystemOrbits.NominalRadius`.
    ---
    Le serveur ne stocke pas les orbites. Il donne un rang, et les deux clients
    en tirent une distance : une console qui ecarterait ses anneaux autrement
    montrerait un systeme que le jeu ne montre pas.
    """
    assert rules['orbits'] == [1600, 2000, 2400, 3600]


def test_une_position_enregistree_l_emporte_sur_le_rang(rules):
    """
    Quand le serveur tient une position, c'est elle qui fait foi.
    ---
    Le rang n'est qu'un repli. Preferer le rang a une position connue
    dessinerait un monde ailleurs que la ou le jeu le pose.
    """
    assert rules['placed'] == {'radius': 3000, 'placed': True}
    assert rules['ranked'] == {'radius': 2000, 'placed': False}


def test_un_systeme_ne_touche_pas_son_voisin(rules):
    """
    Le rayon dessine se tire de l'ecartement des etoiles, et reste dessous.
    ---
    Deux couronnes qui se chevauchent ne se lisent plus comme deux systemes,
    mais comme une toile. La marge n'est pas negociable ; sa valeur exacte,
    si -- d'ou la comparaison a l'ecartement plutot qu'a un nombre.
    """
    assert rules['spacing'] == 10
    assert 0 < rules['radiusOfTen'] < rules['spacing'] / 2

    # Sans galaxie mesurable, le repli est le plus petit rayon : on montre peu
    # plutot que de recouvrir la carte.
    assert rules['radiusOfNothing'] > 0
    assert rules['radiusOfNothing'] <= rules['radiusOfTen']
    # Et une galaxie a deux etoiles ne donne pas un systeme grand comme elle.
    assert rules['radiusOfHuge'] <= 14


def test_le_plan_tient_dans_la_place_donnee(rules):
    """
    Le monde le plus lointain touche exactement le bord, les autres sont dedans.
    ---
    Et chaque monde est pose SUR son anneau : un decalage entre le trace et le
    corps se lit comme une planete qui a glisse de son orbite.
    """
    rings = [p['ring'] for p in rules['plan']]
    assert max(rings) == pytest.approx(8)
    assert all(0 < r <= 8 for r in rings)
    assert all(p['radial'] == pytest.approx(p['ring']) for p in rules['plan'])

    # Du plus proche au plus lointain : les anneaux se peignent dans cet ordre.
    assert rules['planSorted']

    # Rien a dessiner, ou nulle part ou le faire : on s'abstient. Un systeme
    # dessine a une taille devinee se reorganiserait a l'arrivee des vraies
    # donnees, exactement la ou le joueur regarde.
    assert rules['planOfNothing'] == 0
    assert rules['planWithoutRoom'] == 0


def test_la_descente_est_continue_et_ordonnee(rules):
    """
    Le depliage monte de 0 a 1 sans sauter, et les trois seuils sont ranges.
    ---
    Un saut se lit comme un defaut de rendu plutot que comme une arrivee. Et le
    fond de la descente est APRES le depliage complet : atteindre le fond sans
    avoir fini de deplier laisserait le joueur au plus pres d'un systeme a
    moitie peint.
    """
    bounds = rules['bounds']
    assert bounds['open'] < bounds['full'] < bounds['deepest']

    assert rules['unfoldBelow'] == 0
    assert rules['unfoldAt'] == 0
    assert rules['unfoldAbove'] == 1
    assert rules['monotone']
    assert rules['biggestStep'] < 0.05


def test_ce_qui_arrive_et_ce_qui_s_en_va_sont_le_meme_nombre(rules):
    """
    L'effacement de la galaxie est le depliage lu a l'envers.
    ---
    Deux rampes reglees separement rouvrent le defaut au premier ajustement :
    soit on efface la galaxie alors qu'on la regarde encore, soit on peint un
    systeme par-dessus un reseau qui n'a pas fini de partir.

    Et le fond n'est pas zero : rien n'occulte rien sur une carte a plat, et les
    liaisons restantes disent ou l'on se trouve dans la galaxie.
    """
    pairs = dict((r, dim) for r, dim in rules['dimPairs'])
    assert pairs[0] == 1
    assert 0 < pairs[1] < 0.3
    # Lineaire entre les deux : un seul nombre, aucune seconde courbe a regler.
    assert pairs[0.5] == pytest.approx((pairs[0] + pairs[1]) / 2)
    assert pairs[0.25] > pairs[0.5] > pairs[0.75]

    # Une valeur hors bornes ne fait pas sortir l'opacite de la sienne.
    assert rules['dimClamped'] == [1, pairs[1]]


def test_le_systeme_deplie_ne_clignote_pas(rules):
    """
    Qui se deplie : le designe, sinon le plus proche du centre, avec une marge.
    ---
    Sans cette marge, deux etoiles a egale distance du centre se volent le
    systeme a chaque image et l'on voit deux couronnes clignoter l'une contre
    l'autre. Avec elle, celle qu'on tient garde sa place tant que l'autre n'est
    pas NETTEMENT plus proche.
    """
    assert rules['nearest'] == 1
    assert rules['kept'] == 2, "l'etoile tenue cede sa place a un cheveu pres"
    assert rules['picked'] == 1, "une etoile designee l'emporte sur toutes"
    assert rules['stolen'] == 1, "une etoile bien plus proche doit prendre la place"


def test_rien_ne_se_deplie_hors_du_cadre(rules):
    """
    Une etoile hors du cadre n'ouvre pas son systeme.
    ---
    On peindrait des anneaux dont on ne verrait que le bord -- et cela couterait
    une lecture au serveur pour un systeme que personne ne regarde. Cela vaut
    aussi pour une etoile DESIGNEE : la designation survit au deplacement, la
    descente non.
    """
    assert rules['outOfReach'] is None
    assert rules['noStars'] is None
    assert rules['farSelectionIgnored'] == 1
