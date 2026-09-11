# -*- coding: utf-8 -*-

"""
Planet archetypes.

An archetype decides *which* materials a territory can extract at all and in
what base ratios. A per-territory deposit roll then varies the richness, so two
telluric worlds are never quite identical and a gas giant is categorically
different rather than merely poorer.

Material names are plain strings here on purpose: `ResourceType` lives in
`territory`, which imports this module.
"""

import enum
import os
import random

#: Table prefab -> archetype, a la racine du depot. C'est le lien entre ce que
#: le client affiche et ce que la planete produit : le prefab tire par Unity
#: arrive dans `characteristics.planeteScheme`, et cette table le qualifie.
SCHEME_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'planets_archetypes.yml',
)

_scheme_map = None


def _load_scheme_map():
    """
    Lit planets_archetypes.yml.
    ---
    Le fichier est une suite de "Prefab: archetype", sans imbrication : un
    parseur de deux lignes suffit, et evite d'ajouter PyYAML aux dependances
    pour ca.
    """
    mapping = {}
    try:
        with open(SCHEME_MAP_PATH, 'r') as handle:
            for line in handle:
                line = line.split('#', 1)[0].strip()
                if not line or ':' not in line:
                    continue
                scheme, archetype = line.split(':', 1)
                mapping[scheme.strip()] = archetype.strip()
    except IOError:
        # Sans la table, les archetypes sont simplement tires au sort.
        return {}
    return mapping


def scheme_map():
    global _scheme_map
    if _scheme_map is None:
        _scheme_map = _load_scheme_map()
    return _scheme_map

#: Richness drawn per available material at territory creation.
DEPOSIT_MIN = 0.75
DEPOSIT_MAX = 1.25

#: Chance for one material of a territory to sit on a rich vein.
RICH_VEIN_CHANCE = 0.12
RICH_VEIN_FACTOR = 2.0

#: Habitabilite d'un monde de reference, celui qui ne donne ni bonus ni malus.
#: Aucun archetype ne s'y trouve exactement : c'est un etalon, pas une moyenne.
#: Le deplacer rend toute la galaxie plus accueillante ou plus hostile d'un
#: coup, sans toucher au classement des archetypes entre eux.
HABITABILITY_NEUTRAL = 50

#: Rendement de la raffinerie sur un monde parfaitement sec, et ce que cent
#: points d'eau ajoutent par-dessus. Le tritium se tire de l'eau du monde : un
#: monde sans eau en produit encore un peu -- on en fait venir -- mais un
#: oceanique en tire pres du triple.
#:
#: L'ancienne formule portait `(-0.002 * 40 + 1.28)`, une constante ecrite comme
#: une fonction affine de la temperature du monde, evaluee sur un 40 en dur. La
#: temperature n'existait nulle part ailleurs dans le modele : c'est l'eau qui
#: prend sa place. Les bornes sont choisies pour que le monde tellurique -- le
#: seul sur lequel on puisse s'installer -- rende exactement 1.2, ce que valait
#: la constante : l'ouverture de partie ne bouge pas.
WATER_DRY_YIELD = 0.6
WATER_SPAN = 1.0

#: Les deux gestes par lesquels un corps entre dans un empire.
#:
#: `colony` — on y debarque des gens, le monde devient un territoire habite.
#: `station` — on lui arrime une plateforme : elle le possede sans l'habiter.
SETTLEMENT_COLONY = 'colony'
SETTLEMENT_STATION = 'station'

#: L'echelle de colonisation : a partir de quelle habitabilite un monde solide
#: s'ouvre, et ce qu'il faut avoir cherche pour cela.
#:
#: Lue du plus accueillant au plus hostile, et le PREMIER seuil atteint gagne :
#: un monde a 60 tombe dans la premiere ligne et ne demande rien. Les paliers
#: s'appuient sur des technologies qui existent deja — la branche biosphere
#: annoncait ces noms-la depuis toujours sans que rien ne les lise.
COLONISATION_STEPS = [
    # Ocean (80), tellurique (60) : le premier monde et ses semblables.
    (50, None),
    # Desertique (30), volcanique (25) : il faut respirer sous pression.
    (25, {'habitats_pressurises': 2}),
    # Glace (20) : il faut tenir le froid.
    (20, {'adaptation': 3}),
    # Irradiee (13) : il faut reprendre le monde a la racine.
    (13, {'terraformation': 5}),
]


class PlanetArchetype(enum.Enum):
    """
    Yield multipliers applied to the extractor output, per material.

    A material absent from `yields` cannot be extracted on that world at all:
    a gas giant will never produce titanium, whatever the extractor level.
    """

    telluric = {
        'label': 'Tellurique',
        'weight': 22,
        'yields': {'iron': 1.4, 'carbon': 0.9, 'silicium': 0.8, 'titanium': 0.7, 'cristal': 0.4},
        'energy_factor': 1.0,
        'water': 60,
        'habitability': 60,
        'settlement': 'colony',
    }
    volcanic = {
        'label': 'Volcanique',
        'weight': 12,
        'yields': {'iron': 1.8, 'titanium': 1.1, 'silicium': 0.5},
        'energy_factor': 1.25,
        'water': 5,
        'habitability': 25,
        'settlement': 'colony',
    }
    oceanic = {
        'label': 'Océanique',
        'weight': 12,
        'yields': {'carbon': 1.7, 'silicium': 0.9, 'iron': 0.5},
        'energy_factor': 1.0,
        'water': 100,
        'habitability': 80,
        'settlement': 'colony',
    }
    desert = {
        'label': 'Désertique',
        'weight': 12,
        'yields': {'silicium': 1.9, 'cristal': 0.6, 'iron': 0.7},
        'energy_factor': 1.1,
        'water': 2,
        'habitability': 30,
        'settlement': 'colony',
    }
    ice = {
        'label': 'Glacée',
        'weight': 11,
        'yields': {'hydrogen': 1.3, 'carbon': 1.0, 'iron': 0.4},
        'energy_factor': 0.9,
        'water': 85,
        'habitability': 20,
        'settlement': 'colony',
    }
    gas_giant = {
        'label': 'Géante gazeuse',
        'weight': 14,
        'yields': {'hydrogen': 2.6},
        'energy_factor': 1.0,
        'water': 30,
        'habitability': 8,
        # Aucune surface : ne se colonise a aucun palier de l'arbre.
        'settlement': 'station',
        'station_requires': {'forage': 3},
    }
    asteroid = {
        'label': 'Astéroïde',
        'weight': 9,
        'yields': {'titanium': 1.6, 'iron': 1.5, 'uranium': 0.5, 'cristal': 0.5},
        'energy_factor': 0.8,
        'water': 3,
        'habitability': 5,
        'settlement': 'station',
        'station_requires': {'metaux_rares': 4},
    }
    irradiated = {
        'label': 'Irradiée',
        'weight': 7,
        'yields': {'uranium': 1.9, 'iron': 0.9},
        'energy_factor': 1.1,
        'water': 10,
        'habitability': 13,
        'settlement': 'colony',
    }
    anomaly = {
        'label': 'Anomalie',
        'weight': 1,
        'yields': {'neutronium': 0.6, 'cristal': 1.0, 'titanium': 0.7},
        'energy_factor': 1.0,
        'water': 25,
        'habitability': 25,
        # Vingt-cinq, c'est vivable. Mais une anomalie est le seul endroit
        # du jeu qui rende du neutronium : en faire une colonie ordinaire
        # la banaliserait. On la surveille, on ne s'y installe pas.
        'settlement': 'station',
        'station_requires': {'capteurs_gravimetriques': 3},
    }

    def __str__(self):
        return self.name

    @property
    def label(self):
        return self.value['label']

    # ── Comment on prend ce monde ───────────────────────────────────────────

    @property
    def settlement(self):
        """
        Le geste que ce corps accepte : `colony` ou `station`.

        Le partage ne se fait PAS sur l'habitabilite seule. Une regle fondee sur
        elle finirait par rendre les geantes gazeuses colonisables en haut de
        l'arbre — Terraformation descend le seuil jusqu'a 13, et une geante est
        a 8. Un corps sans surface ne se colonise a aucun palier, quelle que
        soit la technologie ; l'habitabilite decide seulement QUAND un monde
        solide s'ouvre.
        """
        return self.value.get('settlement', SETTLEMENT_COLONY)

    @property
    def is_colonisable(self):
        """Ce corps peut-il porter une colonie, un jour ?"""
        return self.settlement == SETTLEMENT_COLONY

    @property
    def station_requires(self):
        """
        Technologies exigees pour y arrimer une plateforme.
        ---
        Vide pour un corps colonisable : il n'accepte pas de station.
        """
        return dict(self.value.get('station_requires') or {})

    def colonisation_requires(self):
        """
        Ce qu'il faut avoir cherche pour s'installer ici.
        ---
        Rend `{}` pour un monde accueillant — au-dessus du premier seuil, il
        n'y a rien a chercher. Rend `None` pour un corps qui ne se colonise
        jamais : l'appelant doit distinguer « pas encore » de « jamais », parce
        que les deux refus n'envoient pas le joueur au meme endroit.
        """
        if not self.is_colonisable:
            return None

        habitability = self.habitability
        for threshold, required in COLONISATION_STEPS:
            if habitability >= threshold:
                return dict(required or {})

        # Un archetype colonisable sous le dernier seuil : la table des paliers
        # et celle des archetypes ont diverge. On refuse plutot que d'ouvrir un
        # monde que personne n'a pese.
        return None

    @property
    def yields(self):
        return self.value['yields']

    @property
    def materials(self):
        """Materials this archetype can produce, in yield order."""
        return list(self.value['yields'].keys())

    @property
    def energy_factor(self):
        return self.value.get('energy_factor', 1.0)

    @property
    def habitability(self):
        """
        A quel point ce monde se laisse habiter, en pourcentage.

        C'est le seul chiffre que le joueur ait a lire pour juger un monde, et
        celui d'ou sortent les deux effets : ce que la ferme y recolte, et
        combien d'habitants une meme recolte y fait vivre.
        """
        return self.value.get('habitability', HABITABILITY_NEUTRAL)

    @property
    def habitability_factor(self):
        """
        Multiplicateur tire de l'habitabilite, 1.0 pour un monde de reference.

        Au-dessus de HABITABILITY_NEUTRAL c'est un bonus, en dessous un malus :
        le joueur doit pouvoir lire le pourcentage comme un avantage ou un
        handicap, pas comme une penalite dans tous les cas.
        """
        return self.habitability / float(HABITABILITY_NEUTRAL)

    @property
    def water(self):
        """
        Teneur en eau du monde, en pourcentage.

        Une geante gazeuse en a un peu -- de la vapeur dans ses couches
        hautes -- un monde glace en est fait, un desert n'en a presque pas.
        C'est le seul chiffre dont depend la raffinerie.
        """
        return self.value.get('water', 0)

    @property
    def water_factor(self):
        """
        Multiplicateur tire de l'eau, applique a ce que rend la raffinerie.

        Jamais nul : sur un caillou sec on fait venir l'eau, cher et en petite
        quantite, mais le tritium ne disparait pas du jeu pour autant. Un monde
        prive de sa seule source de tritium serait injouable, alors qu'un monde
        pauvre est simplement un mauvais endroit ou raffiner.
        """
        return WATER_DRY_YIELD + WATER_SPAN * self.water / 100.0

    def produces(self, material):
        return material in self.value['yields']

    def roll_deposits(self, rng=None):
        """
        Draw the deposit richness of one territory.
        ---
        :return: material name -> richness multiplier
        """
        rng = rng or random
        deposits = {}
        for material in self.materials:
            deposits[material] = round(rng.uniform(DEPOSIT_MIN, DEPOSIT_MAX), 2)

        # One material at most may sit on a rich vein.
        if deposits and rng.random() < RICH_VEIN_CHANCE:
            lucky = rng.choice(list(deposits.keys()))
            deposits[lucky] = round(deposits[lucky] * RICH_VEIN_FACTOR, 2)

        return deposits

    @classmethod
    def get_by_name(cls, name):
        for archetype in cls:
            if archetype.name == name:
                return archetype
        return None

    @classmethod
    def for_scheme(cls, scheme):
        """
        Archetype d'un prefab, via planets_archetypes.yml.
        ---
        `characteristics.planeteScheme` porte le nom du prefab tire par le
        client : c'est lui qui fait le lien entre l'apparence d'un monde et ce
        qu'il produit. Un prefab absent de la table ne dit rien, et renvoie None.
        """
        if not scheme:
            return None
        return cls.get_by_name(scheme_map().get(scheme))

    @classmethod
    def draw(cls, rng=None):
        """
        Pick an archetype at random, respecting the declared weights.
        ---
        Anomalies stay rare on purpose: they are the only neutronium source.
        """
        rng = rng or random
        archetypes = list(cls)
        weights = [a.value['weight'] for a in archetypes]
        return rng.choices(archetypes, weights=weights, k=1)[0]

    @classmethod
    def serialize_all(cls):
        """Catalogue for the clients: what a world of each kind can produce."""
        return [
            {
                'name': a.name,
                'label': a.label,
                'weight': a.value['weight'],
                'yields': a.yields,
                'energy_factor': a.energy_factor,
                'habitability': a.habitability,
                'habitability_factor': a.habitability_factor,
                'water': a.water,
                'water_factor': a.water_factor,
                # Le geste que ce corps accepte, et ce qu'il exige. Les clients
                # dessinent leur bouton a partir de la plutot que de recopier la
                # regle : une liste d'archetypes colonisables ecrite cote client
                # divergerait au premier equilibrage.
                'settlement': a.settlement,
                'colonisation_requires': a.colonisation_requires(),
                'station_requires': a.station_requires,
            }
            for a in cls
        ]
