# -*- coding: utf-8 -*-

"""
Les archetypes de planetes : ce qu'un monde vaut, avant qu'on y construise.

C'est la table de caracteres du jeu. Elle ne fait rien toute seule -- elle est
lue par l'extracteur, par la ferme, par la raffinerie, par la population -- mais
tout ce qui distingue une colonie d'une autre en sort. Une valeur fausse ici ne
casse rien : elle deregle silencieusement l'equilibre de la partie entiere.

Ces tests portent donc moins sur des nombres precis que sur les invariants qui
tiennent la table debout :

  · les materiaux annonces sont des ressources que le jeu connait. C'est la
    condition pour qu'un extracteur puisse les crediter ;
  · aucun facteur n'est nul. Un monde sans tritium serait injouable -- c'est ce
    qui debloque l'academie, l'usine et le chantier naval ;
  · les tirages au sort restent dans leurs bornes, et se laissent reproduire.

Un chiffre y est verifie a l'unite pres, et un seul : le facteur d'eau du monde
tellurique. Il vaut 1.2 parce que c'est ce que valait la constante qu'il a
remplacee, et c'est ce qui garantit qu'une ouverture de partie n'a pas bouge.
"""

import pytest

from app.models.game.planet import (
    DEPOSIT_MAX, DEPOSIT_MIN, HABITABILITY_NEUTRAL, RICH_VEIN_CHANCE,
    RICH_VEIN_FACTOR, PlanetArchetype)
from app.models.game.territory import ResourceType


class ScriptedRandom(object):
    """
    Un tirage decide d'avance.
    ---
    `roll_deposits` melange trois sources d'alea -- la richesse de chaque
    gisement, la chance d'un filon, le materiau qui en beneficie. Les separer
    est le seul moyen de dire lequel a fait quoi ; d'ou cette doublure plutot
    qu'une graine, qui rendrait le test juste mais illisible.
    """

    def __init__(self, uniform=1.0, random=1.0, choice=None, choices=None):
        self._uniform = uniform
        self._random = random
        self._choice = choice
        self._choices = choices
        self.weights_seen = None

    def uniform(self, low, high):
        assert low <= self._uniform <= high, "le tirage sort de ses bornes"
        return self._uniform

    def random(self):
        return self._random

    def choice(self, population):
        return self._choice if self._choice is not None else population[0]

    def choices(self, population, weights, k):
        self.weights_seen = list(weights)
        return [self._choices if self._choices is not None else population[0]] * k


class TestTheTable:

    def test_every_material_is_a_resource_the_game_knows(self):
        """
        Ce qu'un monde produit doit pouvoir etre credite.
        ---
        `Building.get_hourly_gain` convertit chaque nom de materiau en
        `ResourceType` pour crediter le territoire. Un nom absent de l'enum y
        leverait -- au moment de la production, c'est-a-dire a chaque lecture de
        chaque monde de ce type.
        """
        known = {resource.name for resource in ResourceType.materials()}

        for archetype in PlanetArchetype:
            assert set(archetype.materials) <= known, archetype.name

    def test_every_material_is_also_a_column_the_territory_can_hold(self):
        stocked = {resource.name for resource in ResourceType.stocks()}

        for archetype in PlanetArchetype:
            assert set(archetype.materials) <= stocked, archetype.name

    def test_a_world_produces_only_what_it_declares(self):
        """
        L'absence d'un materiau est une regle, pas une penurie.
        ---
        Aucun niveau d'extracteur ne fera sortir du titane d'une geante gazeuse.
        C'est ce qui donne un interet a coloniser ailleurs.
        """
        assert PlanetArchetype.gas_giant.materials == ['hydrogen']
        assert PlanetArchetype.gas_giant.produces('hydrogen')
        assert not PlanetArchetype.gas_giant.produces('titanium')

    def test_neutronium_comes_from_anomalies_alone(self):
        """
        Le materiau le plus rare n'a qu'une source, elle-meme la plus rare.
        ---
        C'est ce qui fait du vaisseau-mere et de la station orbitale des objectifs
        de fin de partie plutot que des achats.
        """
        producers = [a for a in PlanetArchetype if a.produces('neutronium')]

        assert producers == [PlanetArchetype.anomaly]
        assert PlanetArchetype.anomaly.value['weight'] == min(
            a.value['weight'] for a in PlanetArchetype)

    def test_no_yield_is_zero_or_negative(self):
        for archetype in PlanetArchetype:
            for material, ratio in archetype.yields.items():
                assert ratio > 0, "{}.{}".format(archetype.name, material)

    def test_every_archetype_can_be_drawn(self):
        for archetype in PlanetArchetype:
            assert archetype.value['weight'] > 0, archetype.name


class TestHabitability:

    def test_the_reference_world_neither_helps_nor_hinders(self):
        """
        L'etalon rend 1.0 : au-dessus c'est un bonus, en dessous un malus.
        ---
        Le joueur lit un pourcentage sur la fiche du monde ; il doit pouvoir le
        lire comme un avantage ou un handicap, pas comme une penalite dans tous
        les cas.
        """
        best = max(PlanetArchetype, key=lambda a: a.habitability)
        worst = min(PlanetArchetype, key=lambda a: a.habitability)

        assert best.habitability > HABITABILITY_NEUTRAL > worst.habitability
        assert best.habitability_factor > 1.0 > worst.habitability_factor

    def test_the_factor_follows_the_percentage(self):
        assert PlanetArchetype.oceanic.habitability == 80
        assert PlanetArchetype.oceanic.habitability_factor == 80 / float(
            HABITABILITY_NEUTRAL)

    def test_no_world_is_completely_uninhabitable(self):
        """
        Meme un asteroide nourrit un peu.
        ---
        Un facteur nul mettrait la capacite de population a zero, donc la
        croissance a zero : le monde serait pris pour toujours, sans que rien
        n'indique pourquoi.
        """
        for archetype in PlanetArchetype:
            assert archetype.habitability_factor > 0, archetype.name


class TestWater:

    def test_a_telluric_world_refines_exactly_as_before(self):
        """
        1.2 sur un monde tellurique : la constante qu'il a remplacee.
        ---
        Le seul chiffre de cette table verifie a l'unite pres, et pour une
        raison precise : le monde tellurique est le seul ou l'on puisse
        s'installer, et 1.2 est ce que la raffinerie y rendait quand le
        rendement etait une constante en dur. L'ouverture de partie n'a donc
        pas bouge en gagnant une regle.
        """
        assert PlanetArchetype.telluric.water_factor == pytest.approx(1.2)

    def test_water_orders_the_worlds(self):
        assert (PlanetArchetype.oceanic.water_factor
                > PlanetArchetype.telluric.water_factor
                > PlanetArchetype.desert.water_factor)

    def test_the_driest_world_still_refines(self):
        """
        Sur un caillou sec on fait venir l'eau : cher, mais le tritium existe.
        ---
        Un facteur nul priverait ce monde de sa seule source de tritium, donc de
        l'academie, de l'usine et du chantier naval : il serait injouable, la ou
        il ne doit etre qu'un mauvais endroit ou raffiner.
        """
        for archetype in PlanetArchetype:
            assert archetype.water_factor > 0, archetype.name


class TestDeposits:

    def test_richness_stays_within_its_bounds(self):
        rng = ScriptedRandom(uniform=DEPOSIT_MIN, random=1.0)
        poorest = PlanetArchetype.telluric.roll_deposits(rng=rng)

        rng = ScriptedRandom(uniform=DEPOSIT_MAX, random=1.0)
        richest = PlanetArchetype.telluric.roll_deposits(rng=rng)

        assert set(poorest) == set(PlanetArchetype.telluric.materials)
        assert set(poorest.values()) == {DEPOSIT_MIN}
        assert set(richest.values()) == {DEPOSIT_MAX}

    def test_one_material_at_most_sits_on_a_rich_vein(self):
        """
        Un filon, et un seul : c'est ce qui fait la valeur d'un monde precis.
        ---
        En doubler plusieurs ferait des mondes trop inegaux ; n'en doubler aucun
        rendrait deux telluriques interchangeables.
        """
        archetype = PlanetArchetype.telluric
        lucky = archetype.materials[2]

        rng = ScriptedRandom(uniform=1.0, random=RICH_VEIN_CHANCE / 2, choice=lucky)
        deposits = archetype.roll_deposits(rng=rng)

        assert deposits[lucky] == pytest.approx(RICH_VEIN_FACTOR)
        assert [m for m, v in deposits.items() if v > 1.0] == [lucky]

    def test_without_the_lucky_draw_no_vein_is_doubled(self):
        rng = ScriptedRandom(uniform=1.0, random=RICH_VEIN_CHANCE)
        deposits = PlanetArchetype.telluric.roll_deposits(rng=rng)

        assert set(deposits.values()) == {1.0}

    def test_richness_is_rounded_to_two_decimals(self):
        """
        Deux decimales : la valeur part en JSON et revient au client.
        ---
        Elle est affichee sur la fiche du monde ; dix-sept chiffres apres la
        virgule n'y apprendraient rien a personne et alourdiraient chaque
        reponse.
        """
        rng = ScriptedRandom(uniform=5.0 / 6, random=1.0)
        deposits = PlanetArchetype.telluric.roll_deposits(rng=rng)

        assert set(deposits.values()) == {0.83}


class TestDrawing:

    def test_a_draw_respects_the_declared_weights(self):
        """
        Les poids passent au tirage tels qu'ils sont declares.
        ---
        Ils sont l'equilibre de la carte : c'est par eux qu'une anomalie reste
        exceptionnelle et qu'un monde tellurique reste le cas courant.
        """
        rng = ScriptedRandom()
        drawn = PlanetArchetype.draw(rng=rng)

        assert drawn in list(PlanetArchetype)
        assert rng.weights_seen == [a.value['weight'] for a in PlanetArchetype]


class TestLookup:

    def test_a_world_is_found_by_its_name(self):
        assert PlanetArchetype.get_by_name('oceanic') is PlanetArchetype.oceanic
        assert PlanetArchetype.get_by_name('planete_bonbon') is None
        assert PlanetArchetype.get_by_name(None) is None

    def test_the_prefab_the_client_drew_decides_the_archetype(self):
        """
        L'apparence d'un monde et ce qu'il produit ne peuvent pas diverger.
        ---
        `characteristics.planeteScheme` porte le prefab tire par Unity. C'est la
        table qui le qualifie : sans elle, un client pourrait annoncer une
        apparence de monde glace et un archetype de geante gazeuse.
        """
        assert PlanetArchetype.for_scheme('GasGiant') is PlanetArchetype.gas_giant
        assert PlanetArchetype.for_scheme('Hoth') is PlanetArchetype.ice

    def test_an_unknown_prefab_says_nothing(self):
        """
        Rien plutot qu'un defaut : l'appelant tire alors au sort.
        ---
        Rendre un archetype arbitraire ferait de chaque prefab oublie dans la
        table un monde tellurique, et la carte se peuplerait de mondes
        habitables sans que personne ne le decide.
        """
        assert PlanetArchetype.for_scheme('Nowhere') is None
        assert PlanetArchetype.for_scheme('') is None
        assert PlanetArchetype.for_scheme(None) is None

    def test_the_scheme_table_only_names_archetypes_that_exist(self):
        """
        Le fichier vit a la racine du depot, hors du controle du typeur.
        ---
        Une faute de frappe y est silencieuse : `get_by_name` rend None, le
        prefab retombe sur un tirage au sort, et le monde affiche par le client
        cesse de correspondre a ce qu'il produit.
        """
        from app.models.game.planet import scheme_map

        mapping = scheme_map()
        assert mapping, "la table des prefabs devrait etre lisible"

        for scheme, name in mapping.items():
            assert PlanetArchetype.get_by_name(name) is not None, scheme


class TestCatalogue:

    def test_the_catalogue_describes_every_world(self):
        """
        Ce que le client a besoin de savoir avant de coloniser.
        ---
        Les regles restent au serveur : il n'envoie que des nombres, a charge
        pour le client de les mettre en forme.
        """
        catalogue = PlanetArchetype.serialize_all()

        assert [entry['name'] for entry in catalogue] == [
            a.name for a in PlanetArchetype]

        for entry, archetype in zip(catalogue, PlanetArchetype):
            assert entry['label'] == archetype.label
            assert entry['yields'] == archetype.yields
            assert entry['habitability'] == archetype.habitability
            assert entry['habitability_factor'] == archetype.habitability_factor
            assert entry['water'] == archetype.water
            assert entry['water_factor'] == archetype.water_factor
            assert entry['energy_factor'] == archetype.energy_factor
