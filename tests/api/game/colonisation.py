# -*- coding: utf-8 -*-

"""
Prendre un monde : colonisation, et plateformes orbitales.

Trois fils conducteurs, et ce sont eux qui decident de ce qui est teste :

  · **Le partage se fait sur le sol, pas sur l'habitabilite.** Une regle fondee
    sur elle seule finirait par rendre les geantes gazeuses colonisables en haut
    de l'arbre. On verifie donc qu'aucun palier, si haut soit-il, n'ouvre un
    corps sans surface.

  · **Une coque en orbite, et elle se consomme.** C'est la seule regle neuve du
    modele de flotte, et un vaisseau qui survivrait a sa colonie en fonderait
    une par systeme.

  · **Une plateforme n'est pas une colonie.** Pas de population, donc pas de
    famine ; quatre modules, et pas un de plus.
"""

import pytest

from app.models.game.buildings import BuildingType
from app.models.game.fleet import Fleet
from app.models.game.planet import (
    COLONISATION_STEPS, PlanetArchetype, SETTLEMENT_COLONY, SETTLEMENT_STATION)
from app.models.game.ship import ShipType
from app.models.game.system import System
from app.models.game.territory import CRACKING_RATIO, ORBITAL_MODULES, Territory
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import TechnologyType


# ── Outillage ────────────────────────────────────────────────────────────────

def world(session, base_universe, archetype, position=2):
    """Un monde libre du bon archetype, dans un systeme neuf."""
    system = System.create(
        galaxy=base_universe['galaxy'], position="9_%d_9" % position)
    session.commit()

    territory = system.territories[0]
    territory.archetype = archetype
    territory.deposits = archetype.roll_deposits()
    session.commit()
    return territory


def orbit(session, territory, user, hull, count=1):
    """Pose une flotte du joueur en orbite du monde, chargee de `count` coques."""
    fleet = Fleet.create(
        system_id=territory.system_id, user=user, name="escadre",
        orbiting_territory_id=territory.id)
    fleet.add_ships(ship_type=hull, amount=count)
    session.commit()
    return fleet


def grant(session, user, **levels):
    """Offre des niveaux de technologie, sans rien facturer."""
    Technology.ensure(user=user)
    for name, level in levels.items():
        technology = Technology.get(
            user=user, type=TechnologyType.get_by_name(name))
        for _ in range(level):
            technology.increase(now=True)
    session.commit()


def me(session, base_universe):
    return base_universe['users'][0]['model']


# ── Le partage ───────────────────────────────────────────────────────────────

class TestTheSplitIsAboutGround:

    def test_every_archetype_declares_a_gesture(self):
        for archetype in PlanetArchetype:
            assert archetype.settlement in (SETTLEMENT_COLONY, SETTLEMENT_STATION), \
                archetype.name

    def test_bodies_without_a_surface_are_never_colonisable(self):
        """
        Le test qui garde la regle. Une geante est a 8 d'habitabilite et
        Terraformation descend le seuil a 13 : une regle fondee sur
        l'habitabilite seule finirait par les ouvrir.
        """
        for archetype in (PlanetArchetype.gas_giant, PlanetArchetype.asteroid,
                          PlanetArchetype.anomaly):
            assert archetype.settlement == SETTLEMENT_STATION
            assert archetype.is_colonisable is False
            assert archetype.colonisation_requires() is None

    def test_no_step_reaches_below_the_least_habitable_colony(self):
        """
        Le dernier palier ne doit pas descendre sous l'archetype colonisable le
        moins accueillant, sans quoi il ouvrirait des corps que la table des
        archetypes reserve aux plateformes.
        """
        lowest_step = min(threshold for threshold, _ in COLONISATION_STEPS)
        colonies = [a for a in PlanetArchetype if a.is_colonisable]
        stations = [a for a in PlanetArchetype if not a.is_colonisable]

        assert lowest_step <= min(a.habitability for a in colonies)
        for archetype in stations:
            # Une station peut etre plus habitable qu'un seuil — l'anomalie est
            # a 25 — mais cela ne doit rien ouvrir : c'est `settlement` qui
            # tranche, et lui seul.
            assert archetype.colonisation_requires() is None

    def test_a_welcoming_world_asks_for_nothing(self):
        assert PlanetArchetype.telluric.colonisation_requires() == {}
        assert PlanetArchetype.oceanic.colonisation_requires() == {}

    def test_a_hostile_world_names_what_it_wants(self):
        assert PlanetArchetype.desert.colonisation_requires() == {
            'habitats_pressurises': 2}
        assert PlanetArchetype.ice.colonisation_requires() == {'adaptation': 3}
        assert PlanetArchetype.irradiated.colonisation_requires() == {
            'terraformation': 5}

    def test_each_station_body_names_its_own_technology(self):
        assert PlanetArchetype.gas_giant.station_requires == {'forage': 3}
        assert PlanetArchetype.asteroid.station_requires == {'metaux_rares': 4}
        assert PlanetArchetype.anomaly.station_requires == {
            'capteurs_gravimetriques': 3}

    def test_the_catalogue_carries_the_rule(self, client):
        """
        Les clients dessinent leur bouton a partir du catalogue : une liste
        d'archetypes colonisables recopiee cote client divergerait au premier
        equilibrage.
        """
        for entry in PlanetArchetype.serialize_all():
            assert 'settlement' in entry
            assert 'station_requires' in entry
            assert 'colonisation_requires' in entry


# ── La premiere prise ────────────────────────────────────────────────────────

class TestTheFirstWorld:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_needs_no_hull(self, client, session, base_universe):
        """Un joueur qui n'a rien ne peut pas avoir construit de vaisseau."""
        user = me(session, base_universe)
        for territory in list(user.territories):
            territory.user_id = None
            territory.is_capital = False
        session.commit()

        target = world(session, base_universe, PlanetArchetype.telluric)
        assert client.post('/api/territory/%d' % target.id).status_code == 200
        assert Territory.get(id=target.id).user_id == user.id

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_must_be_telluric(self, client, session, base_universe):
        user = me(session, base_universe)
        for territory in list(user.territories):
            territory.user_id = None
            territory.is_capital = False
        session.commit()

        target = world(session, base_universe, PlanetArchetype.desert)
        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        assert "telluric" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_becomes_the_capital(self, client, session, base_universe):
        """
        Le point fixe du reseau. Sans capitale, l'isolement n'aurait rien a
        quoi se mesurer.
        """
        user = me(session, base_universe)
        for territory in list(user.territories):
            territory.user_id = None
            territory.is_capital = False
        session.commit()

        target = world(session, base_universe, PlanetArchetype.telluric)
        client.post('/api/territory/%d' % target.id)

        assert Territory.get(id=target.id).is_capital is True
        assert Territory.capital_of(
            user=user, galaxy_name=target.galaxy_name).id == target.id


# ── Coloniser ────────────────────────────────────────────────────────────────

class TestColonising:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_second_world_needs_a_colony_ship_in_orbit(
            self, client, session, base_universe):
        target = world(session, base_universe, PlanetArchetype.telluric)

        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        assert "ColonyShip" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_with_the_hull_in_orbit_it_passes(self, client, session, base_universe):
        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.telluric)
        orbit(session, target, user, ShipType.ColonyShip)

        assert client.post('/api/territory/%d' % target.id).status_code == 200
        assert Territory.get(id=target.id).user_id == user.id

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_hull_is_consumed(self, client, session, base_universe):
        """
        Un vaisseau qui survivrait a sa colonie en fonderait une par systeme.
        """
        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.telluric)
        fleet = orbit(session, target, user, ShipType.ColonyShip, count=2)

        client.post('/api/territory/%d' % target.id)

        carried = next(s for s in fleet.ships if s.type == ShipType.ColonyShip)
        assert carried.count == 1

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_colony_is_peopled_by_the_ship(self, client, session, base_universe):
        from app.web.api.game.user import COLONISTS_PER_SHIP

        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.telluric)
        orbit(session, target, user, ShipType.ColonyShip)

        client.post('/api/territory/%d' % target.id)
        assert Territory.get(id=target.id).population == COLONISTS_PER_SHIP

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_hostile_world_is_refused_without_the_technology(
            self, client, session, base_universe):
        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.ice)
        orbit(session, target, user, ShipType.ColonyShip)

        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        assert "adaptation" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_technology_opens_it(self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, adaptation=3)

        target = world(session, base_universe, PlanetArchetype.ice)
        orbit(session, target, user, ShipType.ColonyShip)

        assert client.post('/api/territory/%d' % target.id).status_code == 200

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_gas_giant_is_refused_however_far_the_tree_goes(
            self, client, session, base_universe):
        """
        Terraformation ne l'ouvre pas, et aucune autre non plus : c'est le sol
        qui manque, pas la science.
        """
        user = me(session, base_universe)
        grant(session, user, terraformation=5, adaptation=3,
              habitats_pressurises=2, forage=3)

        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ColonyShip)

        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        # Le refus parle de la plateforme, pas d'une technologie de colonisation.
        assert "ExtractionPlatform" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_world_already_held_is_refused(self, client, session, base_universe):
        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.telluric)
        orbit(session, target, user, ShipType.ColonyShip, count=2)

        assert client.post('/api/territory/%d' % target.id).status_code == 200
        assert client.post('/api/territory/%d' % target.id).status_code == 409

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_second_colony_is_not_a_capital(self, client, session, base_universe):
        user = me(session, base_universe)
        # Le monde de depart de la fixture est attribue hors du chemin de prise
        # et n'est donc capitale de rien. On le tamponne comme le fait la
        # migration sur les bases existantes, sans quoi c'est la seconde colonie
        # qui deviendrait capitale — a juste titre.
        user.territories[0].is_capital = True
        session.commit()

        target = world(session, base_universe, PlanetArchetype.telluric)
        orbit(session, target, user, ShipType.ColonyShip)

        client.post('/api/territory/%d' % target.id)
        assert Territory.get(id=target.id).is_capital is False


# ── Arrimer une plateforme ───────────────────────────────────────────────────

class TestAnchoringAPlatform:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_needs_its_own_technology(self, client, session, base_universe):
        user = me(session, base_universe)
        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)

        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        assert "forage" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_with_the_technology_and_the_hull_it_passes(
            self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, forage=3)

        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)

        assert client.post('/api/territory/%d' % target.id).status_code == 200

        taken = Territory.get(id=target.id)
        assert taken.user_id == user.id
        assert taken.orbital is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_platform_carries_nobody(self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, forage=3)

        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)
        client.post('/api/territory/%d' % target.id)

        taken = Territory.get(id=target.id)
        assert taken.population == 0
        assert taken.population_capacity == 0

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_platform_never_starves(self, client, session, base_universe):
        """
        Sans bouche a nourrir il n'y a pas de famine. Une plateforme ne perd
        donc jamais de stabilite de ce cote — seul le reseau la menace.
        """
        user = me(session, base_universe)
        grant(session, user, forage=3)

        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)
        client.post('/api/territory/%d' % target.id)

        taken = Territory.get(id=target.id)
        taken.food = 0
        taken._run_life_cycle(hours=48.0)

        assert taken.stability_score == 100

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_colony_ship_will_not_anchor_a_platform(
            self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, forage=3)

        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ColonyShip)

        answer = client.post('/api/territory/%d' % target.id)
        assert answer.status_code == 400
        assert "ExtractionPlatform" in answer.json['message']


# ── Ce qu'une plateforme accepte de construire ───────────────────────────────

class TestOrbitalModules:

    def platform(self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, forage=3)
        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)
        client.post('/api/territory/%d' % target.id)
        return Territory.get(id=target.id)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_accepts_only_the_four_modules(self, client, session, base_universe):
        taken = self.platform(client, session, base_universe)

        for building in BuildingType:
            expected = building in ORBITAL_MODULES
            assert taken.accepts(building) is expected, building.name

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_farm_is_refused_with_a_reason(self, client, session, base_universe):
        taken = self.platform(client, session, base_universe)

        answer = client.post('/api/territory/%d/farm' % taken.id)
        assert answer.status_code == 400
        assert "no ground" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_colony_refuses_the_cracker(self, client, session, base_universe):
        """Rien a casser sur un monde qui ne rend pas d'hydrogene."""
        user = me(session, base_universe)
        colony = user.territories[0]
        colony.archetype = PlanetArchetype.telluric
        session.commit()

        assert colony.accepts(BuildingType.gas_cracker) is False

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_ice_world_accepts_the_cracker(self, client, session, base_universe):
        """Une glacee rend de l'hydrogene : elle peut le craquer."""
        user = me(session, base_universe)
        colony = user.territories[0]
        colony.archetype = PlanetArchetype.ice
        session.commit()

        assert colony.accepts(BuildingType.gas_cracker) is True

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_depot_is_behind_no_technology(self, client, session, base_universe):
        """
        Une ligne de commerce est la seule reponse a l'isolement, et
        l'isolement coute de la stabilite. Mettre le depot derriere l'arbre
        reviendrait a punir un joueur pour une recherche qu'il n'a pas pu faire.
        """
        user = me(session, base_universe)
        colony = user.territories[0]
        assert colony.missing_technologies(BuildingType.depot) == {}


# ── Le craqueur ──────────────────────────────────────────────────────────────

class TestCracking:

    def platform(self, client, session, base_universe):
        user = me(session, base_universe)
        grant(session, user, forage=3, raffinage=2)
        target = world(session, base_universe, PlanetArchetype.gas_giant)
        orbit(session, target, user, ShipType.ExtractionPlatform)
        client.post('/api/territory/%d' % target.id)
        return Territory.get(id=target.id)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_without_the_module_nothing_is_cracked(
            self, client, session, base_universe):
        taken = self.platform(client, session, base_universe)
        taken.hydrogen = 10000

        assert taken._run_cracking(hours=1.0) == 0.0
        assert taken.hydrogen == 10000

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_hydrogen_becomes_tritium(self, client, session, base_universe):
        taken = self.platform(client, session, base_universe)
        taken.get_building(building_type=BuildingType.gas_cracker).level = 3
        taken.hydrogen = 100000
        taken.tritium = 0

        made = taken._run_cracking(hours=1.0)

        assert made > 0
        assert taken.tritium == pytest.approx(made)
        assert taken.hydrogen == pytest.approx(100000 - made * CRACKING_RATIO)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_never_takes_more_hydrogen_than_there_is(
            self, client, session, base_universe):
        """
        Le seul batiment dont l'entree est une ressource : sans cette borne, la
        colonne descendrait sous zero.
        """
        taken = self.platform(client, session, base_universe)
        taken.get_building(building_type=BuildingType.gas_cracker).level = 5
        taken.hydrogen = 40
        taken.tritium = 0

        made = taken._run_cracking(hours=10.0)

        assert taken.hydrogen == pytest.approx(0.0)
        assert made == pytest.approx(40 / CRACKING_RATIO)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_it_beats_a_refinery_on_a_dry_world(self, client, session, base_universe):
        """
        C'est toute la raison d'etre d'une plateforme sur geante : l'hydrogene
        n'avait presque aucun debouche, et le tritium verrouille l'academie,
        l'usine et le chantier naval.
        """
        taken = self.platform(client, session, base_universe)
        taken.get_building(building_type=BuildingType.gas_cracker).level = 3

        desert = PlanetArchetype.desert
        refinery_on_dry = (10 + 12 * 3 * pow(1.1, 3)) * desert.water_factor

        assert taken.cracking_capacity > refinery_on_dry * 2
