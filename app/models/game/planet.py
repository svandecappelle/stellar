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
    }
    volcanic = {
        'label': 'Volcanique',
        'weight': 12,
        'yields': {'iron': 1.8, 'titanium': 1.1, 'silicium': 0.5},
        'energy_factor': 1.25,
    }
    oceanic = {
        'label': 'Océanique',
        'weight': 12,
        'yields': {'carbon': 1.7, 'silicium': 0.9, 'iron': 0.5},
        'energy_factor': 1.0,
    }
    desert = {
        'label': 'Désertique',
        'weight': 12,
        'yields': {'silicium': 1.9, 'cristal': 0.6, 'iron': 0.7},
        'energy_factor': 1.1,
    }
    ice = {
        'label': 'Glacée',
        'weight': 11,
        'yields': {'hydrogen': 1.3, 'carbon': 1.0, 'iron': 0.4},
        'energy_factor': 0.9,
    }
    gas_giant = {
        'label': 'Géante gazeuse',
        'weight': 14,
        'yields': {'hydrogen': 2.6},
        'energy_factor': 1.0,
    }
    asteroid = {
        'label': 'Astéroïde',
        'weight': 9,
        'yields': {'titanium': 1.6, 'iron': 1.5, 'uranium': 0.5, 'cristal': 0.5},
        'energy_factor': 0.8,
    }
    irradiated = {
        'label': 'Irradiée',
        'weight': 7,
        'yields': {'uranium': 1.9, 'iron': 0.9},
        'energy_factor': 1.1,
    }
    anomaly = {
        'label': 'Anomalie',
        'weight': 1,
        'yields': {'neutronium': 0.6, 'cristal': 1.0, 'titanium': 0.7},
        'energy_factor': 1.0,
    }

    def __str__(self):
        return self.name

    @property
    def label(self):
        return self.value['label']

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
            }
            for a in cls
        ]
