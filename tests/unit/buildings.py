# -*- coding: utf-8 -*-

"""
Ce qu'un batiment coute et ce qu'il rend.

Deux niveaux se croisent ici, et les melanger est ce qui a deja coute cher :

  · `BuildingType` porte les tables -- des couts et des durees fonctions du
    niveau, identiques partout. Ce sont les regles du jeu ;
  · `Building` est un batiment pose sur un monde precis. C'est la que le monde
    a son mot a dire (l'archetype, les gisements, la stabilite) et que les
    reglages de la galaxie s'appliquent -- a cet endroit et nulle part ailleurs,
    pour que la production creditee et la production annoncee ne puissent pas
    diverger.

Les tests des tables ne recopient pas les formules : ils verifient ce dont le
reste du code depend -- que les cles nomment des ressources qui existent, que
les couts montent avec le niveau. C'est une erreur de cle qui rendait autrefois
chaque batiment gratuit en credits, et aucune formule verifiee a la virgule ne
l'aurait vue.
"""

import pytest

from app.models.game.buildings import BuildingType
from app.models.game.planet import PlanetArchetype
from app.models.game.territory import ResourceType


class TestTheTables:

    def test_every_cost_names_a_resource_the_game_knows(self):
        """
        Une cle inconnue est un cout qui ne se paie jamais.
        ---
        `get_resource_cost` cherche la ressource par son nom et rend zero quand
        elle manque. Les couts s'ecrivaient 'credit' la ou l'enum dit 'credits' :
        chaque batiment du jeu etait gratuit en credits, en silence.
        """
        known = {resource.name for resource in ResourceType}

        for building in BuildingType:
            assert set(building.value['cost']) <= known, building.name

    def test_every_gain_names_a_resource_the_game_knows(self):
        known = {resource.name for resource in ResourceType}

        for building in BuildingType:
            assert set(building.value.get('gain', {})) <= known, building.name

    def test_every_building_costs_something_and_takes_time(self):
        for building in BuildingType:
            costs = building.get_cost(level=1)
            assert any(amount > 0 for amount in costs.values()), building.name
            assert building.duration(level=0) > 0, building.name

    def test_a_cost_covers_every_resource_even_those_it_does_not_ask(self):
        """
        Un cout complet, avec des zeros : c'est ce que compare le prerequis.
        ---
        `match_prerequisite` parcourt les cles qu'on lui donne ; une table
        partielle marcherait aussi, mais la serialisation enverrait au client un
        cout different d'un batiment a l'autre, a lui de deviner les absents.
        """
        costs = BuildingType.farm.get_cost(level=1)

        assert set(costs) == set(ResourceType)
        assert costs[ResourceType.neutronium] == 0

    def test_the_next_level_always_costs_more(self):
        for building in BuildingType:
            for level in range(1, 5):
                cheaper = building.get_cost(level=level)
                dearer = building.get_cost(level=level + 1)
                asked = [r for r, amount in cheaper.items() if amount > 0]
                assert asked, building.name
                for resource in asked:
                    assert dearer[resource] > cheaper[resource], (
                        building.name, resource.name, level)

    def test_the_next_level_always_takes_longer(self):
        for building in BuildingType:
            for level in range(0, 5):
                assert building.duration(level + 1) > building.duration(level)

    def test_a_producer_yields_more_at_each_level(self):
        producers = [b for b in BuildingType if b.value.get('gain')]
        assert producers, "le jeu devrait avoir des batiments producteurs"

        for building in producers:
            for resource in building.type_of_resource:
                for level in range(0, 5):
                    assert building.get_resource_gain(resource, level + 1) > \
                        building.get_resource_gain(resource, level), (
                            building.name, resource.name, level)

    def test_three_buildings_yield_something_from_the_first_hour(self):
        """
        Centrale, ferme et raffinerie donnent un fond des le niveau zero.
        ---
        Un monde habite mange avant de savoir construire, et il lui faut de
        quoi payer son premier batiment. La raffinerie a rejoint les deux
        autres : elle rendait 10 au niveau 0 et 13.2 au niveau 1, soit
        quarante-cinq heures pour amortir un palier qui verrouille l'academie,
        l'usine et le chantier naval.
        """
        for building in (BuildingType.power_station, BuildingType.farm,
                         BuildingType.rafinery):
            resource = building.type_of_resource[0]
            assert building.get_resource_gain(resource, 0) > 0, building.name

    def test_only_one_building_extracts(self):
        """
        Un seul extracteur : ce qu'il remonte depend du monde, pas du batiment.
        ---
        C'est ce qui permet a la meme construction de rendre du titane sur un
        asteroide et de l'hydrogene sur une geante gazeuse.
        """
        extractors = [b for b in BuildingType if b.is_extractor]

        assert extractors == [BuildingType.mater_extractor]
        assert BuildingType.mater_extractor.get_extraction(level=0) > 0
        assert BuildingType.power_station.get_extraction(level=3) == 0

    def test_a_building_is_found_by_its_name(self):
        assert BuildingType.get_by_name('farm') is BuildingType.farm
        assert str(BuildingType.farm) == 'farm'


class TestWhatAWorldYields:

    def test_an_extractor_splits_its_output_over_the_local_materials(
            self, make_territory):
        """
        L'extracteur rend ce que le sol contient, dans les proportions du monde.
        ---
        Le batiment ne sait rien produire par lui-meme : il a un debit, et c'est
        l'archetype croise aux gisements qui dit en quoi ce debit se convertit.
        """
        territory = make_territory(archetype=PlanetArchetype.telluric)
        extractor = territory.get_building(BuildingType.mater_extractor)
        extractor.level = 3

        rate = BuildingType.mater_extractor.get_extraction(level=3)
        gains = extractor.get_hourly_gain

        for material, factor in territory.material_yields.items():
            assert gains[ResourceType(material)] == pytest.approx(rate * factor)

    def test_a_gas_giant_yields_nothing_but_hydrogen(self, make_territory):
        territory = make_territory(archetype=PlanetArchetype.gas_giant)
        extractor = territory.get_building(BuildingType.mater_extractor)
        extractor.level = 2

        gains = extractor.get_hourly_gain

        assert gains[ResourceType.hydrogen] > 0
        assert gains[ResourceType.iron] == 0
        assert gains[ResourceType.titanium] == 0

    def test_a_rich_vein_yields_more_than_a_poor_one(self, make_territory):
        """
        Deux mondes du meme archetype ne se valent pas.
        ---
        La richesse tiree a la creation multiplie le rendement de l'archetype :
        c'est ce qui donne un interet a comparer deux telluriques.
        """
        poor = make_territory(deposits={'iron': 0.75})
        rich = make_territory(deposits={'iron': 1.5})

        for territory in (poor, rich):
            territory.get_building(BuildingType.mater_extractor).level = 2

        yielded = [t.get_building(BuildingType.mater_extractor)
                    .get_hourly_gain[ResourceType.iron] for t in (poor, rich)]

        assert yielded[1] == pytest.approx(yielded[0] * 2)

    def test_a_material_the_world_lacks_is_never_extracted(self, make_territory):
        """
        Un gisement declare pour un materiau que l'archetype ne produit pas ne
        cree rien : c'est l'archetype qui tranche.
        """
        territory = make_territory(
            archetype=PlanetArchetype.gas_giant,
            deposits={'hydrogen': 1.0, 'neutronium': 10.0})
        territory.get_building(BuildingType.mater_extractor).level = 4

        gains = territory.get_building(BuildingType.mater_extractor).get_hourly_gain

        assert gains[ResourceType.neutronium] == 0

    def test_a_farm_feeds_by_the_habitability_of_its_world(self, make_territory):
        """
        Une geante gazeuse ne nourrit personne, quel que soit le niveau.
        """
        temperate = make_territory(archetype=PlanetArchetype.oceanic)
        barren = make_territory(archetype=PlanetArchetype.gas_giant)

        harvests = []
        for territory in (temperate, barren):
            farm = territory.get_building(BuildingType.farm)
            farm.level = 3
            harvests.append(farm.get_hourly_gain[ResourceType.food])

        base = BuildingType.farm.get_resource_gain(ResourceType.food, 3)
        assert harvests[0] == pytest.approx(
            base * PlanetArchetype.oceanic.habitability_factor)
        assert harvests[1] < harvests[0]

    def test_a_refinery_draws_tritium_from_the_water_of_its_world(
            self, make_territory):
        """
        Le seul terme qui fasse varier une raffinerie d'un endroit a l'autre.
        ---
        Sans lui, elle rendait la meme chose sur un oceanique et sur un caillou
        sec, et le choix du monde ou raffiner n'existait pas.
        """
        wet = make_territory(archetype=PlanetArchetype.oceanic)
        dry = make_territory(archetype=PlanetArchetype.desert)

        outputs = []
        for territory in (wet, dry):
            refinery = territory.get_building(BuildingType.rafinery)
            refinery.level = 2
            outputs.append(refinery.get_hourly_gain[ResourceType.tritium])

        base = BuildingType.rafinery.get_resource_gain(ResourceType.tritium, 2)
        assert outputs[0] == pytest.approx(
            base * PlanetArchetype.oceanic.water_factor)
        assert outputs[1] == pytest.approx(
            base * PlanetArchetype.desert.water_factor)
        assert outputs[0] > outputs[1] > 0

    def test_an_extractor_reports_what_this_world_lets_it_dig(self, make_territory):
        """
        Le meme batiment n'alimente pas les memes ressources partout.
        ---
        C'est par cette liste que le territoire sait quels batiments compter
        dans la production d'une ressource donnee.
        """
        territory = make_territory(archetype=PlanetArchetype.asteroid)
        extractor = territory.get_building(BuildingType.mater_extractor)

        assert set(extractor.type_of_resource) == {
            ResourceType(m) for m in PlanetArchetype.asteroid.materials}


class TestUnrest:

    def test_an_angry_world_produces_less(self, make_territory):
        """
        La stabilite rogne la production, sans jamais l'arreter.
        ---
        Un plancher est indispensable : a zero, plus rien ne pourrait sortir le
        monde de la ou il est tombe.
        """
        calm = make_territory(stability=100)
        angry = make_territory(stability=0)

        outputs = []
        for territory in (calm, angry):
            centre = territory.get_building(BuildingType.economical_center)
            centre.level = 4
            outputs.append(centre.get_hourly_gain[ResourceType.credits])

        assert outputs[1] == pytest.approx(outputs[0] * angry.stability_factor)
        assert 0 < outputs[1] < outputs[0]

    def test_food_and_energy_are_spared_by_unrest(self, make_territory):
        """
        Deux exceptions, et elles ont la meme raison : sans elles, une famine
        serait sans retour.
        ---
        La nourriture est la seule sortie d'une famine ; l'energie n'est pas un
        stock mais un plafond -- la rogner retirerait au joueur des batiments
        deja payes, et l'empecherait de monter la ferme qui le sauverait.
        """
        calm = make_territory(stability=100)
        angry = make_territory(stability=0)

        for territory in (calm, angry):
            territory.get_building(BuildingType.farm).level = 3
            territory.get_building(BuildingType.power_station).level = 3

        for building_type, resource in (
                (BuildingType.farm, ResourceType.food),
                (BuildingType.power_station, ResourceType.energy)):
            assert (angry.get_building(building_type).get_hourly_gain[resource]
                    == pytest.approx(
                        calm.get_building(building_type).get_hourly_gain[resource]))


class TestGalaxySettingsOnBuildings:

    def test_the_extraction_setting_lifts_the_extractor_alone(
            self, make_territory, tune):
        """
        Le rendement des extracteurs n'agit que sur ce qui sort du sol.
        ---
        Ce que rendent la centrale, la raffinerie ou le centre economique n'en
        depend pas : c'est ce qui distingue ce reglage de la production generale.
        """
        tune(extraction_multiplier=3.0)
        territory = make_territory()
        territory.get_building(BuildingType.mater_extractor).level = 2
        territory.get_building(BuildingType.power_station).level = 2

        extracted = territory.get_building(
            BuildingType.mater_extractor).get_hourly_gain[ResourceType.iron]
        generated = territory.get_building(
            BuildingType.power_station).get_hourly_gain[ResourceType.energy]

        expected = (BuildingType.mater_extractor.get_extraction(level=2) * 3.0
                    * territory.material_yields['iron'])
        assert extracted == pytest.approx(expected)
        assert generated == pytest.approx(
            BuildingType.power_station.get_resource_gain(ResourceType.energy, 2))

    def test_the_general_setting_lifts_everything(self, make_territory, tune):
        """
        Production generale : extraction comprise, les deux se multipliant.
        ---
        C'est le reglage a bouger pour accelerer une partie entiere.
        """
        tune(extraction_multiplier=2.0, resource_gain_multiplier=5.0)
        territory = make_territory()
        territory.get_building(BuildingType.mater_extractor).level = 2
        territory.get_building(BuildingType.economical_center).level = 2

        extracted = territory.get_building(
            BuildingType.mater_extractor).get_hourly_gain[ResourceType.iron]
        earned = territory.get_building(
            BuildingType.economical_center).get_hourly_gain[ResourceType.credits]

        assert extracted == pytest.approx(
            BuildingType.mater_extractor.get_extraction(level=2)
            * territory.material_yields['iron'] * 2.0 * 5.0)
        assert earned == pytest.approx(
            BuildingType.economical_center.get_resource_gain(
                ResourceType.credits, 2) * 5.0)

    def test_the_cost_setting_moves_the_price_of_the_next_level(
            self, make_territory, tune):
        """
        Le cout annonce est celui qu'on paie : un seul calcul pour les deux.
        ---
        `Territory.can_be_increased` et la serialisation lisent la meme
        propriete. Deux chemins separes finiraient par diverger, et le joueur
        paierait autre chose que ce qu'il a lu.
        """
        tune(building_cost_multiplier=0.5)
        territory = make_territory()
        farm = territory.get_building(BuildingType.farm)
        farm.level = 2

        catalogue = BuildingType.farm.get_cost(level=3)
        assert farm.cost[ResourceType.iron] == pytest.approx(
            catalogue[ResourceType.iron] * 0.5)

    def test_a_cost_is_always_the_price_of_the_level_to_come(self, make_territory):
        territory = make_territory()
        farm = territory.get_building(BuildingType.farm)
        farm.level = 4

        assert farm.cost == BuildingType.farm.get_cost(level=5)

    def test_the_build_time_setting_divides_the_wait(self, make_territory, tune):
        tune(build_time_divider=4.0)
        territory = make_territory()
        farm = territory.get_building(BuildingType.farm)
        farm.level = 2

        assert farm.next_level_duration == pytest.approx(
            BuildingType.farm.duration(level=2) / 4.0)

    def test_a_factory_speeds_up_every_yard_on_the_world(self, make_territory):
        """
        L'usine divise l'attente de tout ce qui se construit sur le monde.
        ---
        C'est le seul batiment dont l'effet porte sur les autres : sans elle,
        les paliers hauts se paieraient en jours.
        """
        territory = make_territory()
        farm = territory.get_building(BuildingType.farm)
        farm.level = 2

        alone = farm.next_level_duration
        territory.get_building(BuildingType.factory).level = 3

        assert farm.next_level_duration == pytest.approx(alone / 4)


class TestConsumption:

    def test_a_building_consumes_what_its_current_level_cost_in_energy(
            self, make_territory):
        """
        Le cout en energie d'un batiment est sa consommation permanente.
        ---
        L'energie n'est pas un stock mais un solde : elle n'est pas debitee a la
        construction, elle est retenue tant que le batiment tient debout.
        """
        territory = make_territory()
        extractor = territory.get_building(BuildingType.mater_extractor)
        extractor.level = 3

        assert extractor.consumption == pytest.approx(
            BuildingType.mater_extractor.get_cost(
                level=3)[ResourceType.energy])

    def test_the_available_energy_is_the_station_minus_the_rest(
            self, make_territory):
        territory = make_territory()
        territory.get_building(BuildingType.power_station).level = 4
        territory.get_building(BuildingType.mater_extractor).level = 2

        produced = territory.get_building(
            BuildingType.power_station).get_hourly_gain[ResourceType.energy]
        consumed = sum(b.consumption for b in territory.buildings)

        assert territory.energy == pytest.approx(produced - consumed)
        assert consumed > 0
