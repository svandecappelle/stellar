import datetime

import pytest

from freezegun import freeze_time

from app.models.game.buildings import BuildingType
from app.models.game.planet import PlanetArchetype
from app.models.game.territory import (
    FOOD_PER_POPULATION_HOUR,
    ResourceType,
    Territory,
)


class TestTerritory:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_new_user_has_territory(self, client):
        """
        Test new user have a territory
        ---
        :param client: http client
        """

        response = client.get(
            '/api/technologies/events'
        )
        assert response.status_code == 200
        assert len(response.json) == 0

        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0].get('id') is not None

    @pytest.mark.parametrize('resource', (
        (ResourceType.iron, 10000),
        (ResourceType.credits, 8000),
        (ResourceType.population, 100),
        (ResourceType.tritium, 100),
        (ResourceType.food, 1000),
        (ResourceType.energy, 13)
    ))
    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_resources_on_territory_at_start(self, client, resource):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0].get('id') is not None

        # Check starting resource
        territory = Territory.get(id=response.json[0]["id"])
        assert territory.resources[resource[0]] == resource[1]

    @pytest.mark.parametrize('resource', (
        (ResourceType.iron, 10000, BuildingType.mater_extractor),
        (ResourceType.credits, 8000, BuildingType.economical_center),
        # (ResourceType.population, 100, None),  # TODO define how population can increase
        (ResourceType.tritium, 100, BuildingType.rafinery)
    ))
    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_resources_increase_on_territory(self, client, resource, session):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0].get('id') is not None

        # Check starting resource and set level of building to 1
        territory = Territory.get(id=response.json[0]["id"])
        territory.add(type=resource[2], amount=1)
        session.commit()
        assert territory.resources[resource[0]] == resource[1]

        # wait one second and check if resources increased on territory before last update

        # increase datetime to simulate future time
        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(seconds=1000))

            territory.update_view()
            resource_amount = territory.resources[resource[0]]
            assert resource_amount > resource[1]

            # wait again for a refresh and check resource has been updated between previous state
            frozen_datetime.tick(datetime.timedelta(seconds=1000))

            territory.update_view()
            assert territory.resources[resource[0]] > resource_amount

    @pytest.mark.parametrize('resource', (
            (ResourceType.iron, 10000, BuildingType.mater_extractor),
            (ResourceType.credits, 8000, BuildingType.economical_center),
            # (ResourceType.population, 100, None),  # TODO define how population can increase
            (ResourceType.tritium, 100, BuildingType.rafinery)
    ))
    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_increase_level_building_on_territory(self, client, resource):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)
        # Add energy to ensure have prerequisites on energy
        territory.add(type=BuildingType.power_station, amount=1)

        response = client.post(
            f'/api/territory/{territory_id}/{resource[2].name}'
        )
        assert response.status_code == 200

        assert response.json['eventType'] == 'PositionalEventType.building'
        assert response.json['extraArgs'] == {'name': resource[2].name, 'level': 0}

        # level is still 0 until event is finished
        assert [b.level for b in territory.buildings if b.type == resource[2]][0] == 0

        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # increase datetime to simulate future time
        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(seconds=1000))

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == 0

            assert [b.level for b in territory.buildings if b.type == resource[2]][0] == 1

    @pytest.mark.parametrize("building", [b for b in BuildingType])
    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_factory_reduce_time_of_building(self, client, session, building):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)
        # Add energy to ensure have prerequisites on energy
        if building != BuildingType.power_station:
            territory.add(type=BuildingType.power_station, amount=1)
        if building in (BuildingType.shipyard, BuildingType.academy, BuildingType.factory):
            territory.add(type=ResourceType.tritium, amount=400)

        response = client.get(
            f'/api/territory/{territory_id}'
        )
        assert response.status_code == 200
        # get duration
        duration_of_lvl = response.json['buildings'][building.name]['duration']
        assert duration_of_lvl > 0

        # increase building
        response = client.post(
            f'/api/territory/{territory_id}/{building.name}'
        )
        assert response.status_code == 200
        assert response.json['eventType'] == 'PositionalEventType.building'
        assert response.json['extraArgs'] == {'name': building.name, 'level': 0}

        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # increase datetime to simulate future time
        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(seconds=1000))

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == 0

            assert [b.level for b in territory.buildings if b.type == building][0] == 1

        response = client.get(
            f'/api/territory/{territory_id}'
        )
        assert response.status_code == 200
        # get new duration
        duration_of_next_lvl = response.json['buildings'][building.name]['duration']
        assert duration_of_lvl < duration_of_next_lvl

        territory.add(type=BuildingType.factory, amount=1)
        session.commit()
        response = client.get(
            f'/api/territory/{territory_id}'
        )
        assert response.status_code == 200
        # get new duration
        duration_of_next_lvl_with_factory_increased = response.json['buildings'][building.name]['duration']
        if building == BuildingType.factory:
            # Factory is not concerned by gain of increased factory
            assert duration_of_next_lvl_with_factory_increased > duration_of_next_lvl
        else:
            assert duration_of_next_lvl_with_factory_increased < duration_of_next_lvl


class TestRaiseTerritory:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_not_my_territory(self, client):
        """
        Test new user have a territory
        ---
        :param client: http client
        """

        response = client.get(
            '/api/technologies/events'
        )
        assert response.status_code == 200
        assert len(response.json) == 0

        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0].get('id') is not None

        # Add event using increase a tech
        response = client.post(
            f'/api/technology/computer/666'
        )
        assert response.status_code == 400
        assert response.json['message'] == "Territory does not owned by you"


class TestTerritoryLifeCycle:
    """
    Nourriture, population et stabilite : la boucle jouee a chaque `update_view`.

    Les trois se tiennent — la ferme nourrit, la population mange et croit, la
    famine ronge la stabilite — et c'est le lien entre elles qu'on verifie ici,
    pas chaque grandeur prise separement.
    """

    @staticmethod
    def _own_territory(client):
        response = client.get('/api/territories')
        assert response.status_code == 200
        assert len(response.json) == 1
        return Territory.get(id=response.json[0]["id"])

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_food_is_produced_by_the_farm(self, client, session):
        territory = self._own_territory(client)
        base = territory.get_hourly_gain(resource_type=ResourceType.food)
        assert base > 0, "une ferme de niveau 0 nourrit deja un peu"

        territory.add(type=BuildingType.farm, amount=2)
        session.commit()
        assert territory.get_hourly_gain(resource_type=ResourceType.food) > base

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_population_grows_while_fed(self, client, session):
        territory = self._own_territory(client)
        # Une ferme de bon niveau : la limite doit depasser largement les 100
        # habitants de depart, sinon la croissance n'a nulle part ou aller.
        territory.add(type=BuildingType.farm, amount=4)
        session.commit()
        assert territory.population_capacity > territory.population

        before = territory.population
        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(hours=5))
            territory.update_view()

        assert territory.population > before
        assert territory.stability == 100
        assert territory.food > 0

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_population_stalls_and_stability_falls_without_food(self, client, session):
        territory = self._own_territory(client)
        # Reserve vide et bien plus de bouches que la recolte n'en couvre :
        # c'est exactement la famine.
        territory.food = 0
        territory.population = territory.population_capacity * 10 + 1000
        session.commit()

        population_before = territory.population
        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(hours=6))
            territory.update_view()

        assert territory.is_starving
        assert territory.population == population_before, "la population stagne, elle ne meurt pas"
        assert territory.stability < 100

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_stability_recovers_once_fed_again(self, client, session):
        territory = self._own_territory(client)
        territory.stability = 20
        territory.add(type=BuildingType.farm, amount=4)
        session.commit()

        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(hours=5))
            territory.update_view()

        assert territory.stability > 20

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_low_stability_slows_production_but_never_the_harvest(self, client, session):
        territory = self._own_territory(client)
        territory.add(type=BuildingType.mater_extractor, amount=3)
        territory.add(type=BuildingType.farm, amount=3)
        session.commit()

        iron_at_peace = territory.get_hourly_gain(resource_type=ResourceType.iron)
        food_at_peace = territory.get_hourly_gain(resource_type=ResourceType.food)

        territory.stability = 0
        session.commit()

        assert territory.get_hourly_gain(resource_type=ResourceType.iron) < iron_at_peace
        # La recolte est exemptee : la penaliser rendrait toute famine definitive.
        assert territory.get_hourly_gain(resource_type=ResourceType.food) == food_at_peace

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_serialized_territory_carries_the_life_cycle(self, client):
        territory = self._own_territory(client)
        response = client.get(f'/api/territory/{territory.id}')
        assert response.status_code == 200

        # `update_view` tourne dans la vue : la reserve a pu bouger d'un cheveu.
        assert response.json['resources']['food'] > 0
        assert response.json['resources']['stability'] == 100
        assert response.json['stability'] == 100
        # Ce que la population prend chaque heure, en face de ce que la ferme rend.
        assert response.json['upkeep']['food'] > 0
        assert response.json['population_capacity'] > 0
        assert response.json['habitability'] > 0
        assert response.json['habitability_factor'] > 0
        assert response.json['energy_factor'] > 0
        assert response.json['starving'] is False

    # ── Horloge de rattrapage ───────────────────────────────────────────────

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_long_absence_is_credited_in_full(self, client, session):
        """
        Trois jours d'absence valent trois jours de production.

        `timedelta.seconds` ne rend que le reste au-dela des journees entieres :
        trois jours pile rendaient zero heure, et vingt-cinq heures en rendaient
        une. C'est `total_seconds()` qu'il faut, et ce test est la pour que ca
        le reste.
        """
        territory = self._own_territory(client)
        territory.add(type=BuildingType.mater_extractor, amount=1)
        session.commit()

        hourly = territory.get_hourly_gain(resource_type=ResourceType.iron)
        assert hourly > 0
        before = territory.resources[ResourceType.iron]

        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(days=3))
            territory.update_view()

        credited = territory.resources[ResourceType.iron] - before
        assert credited == pytest.approx(hourly * 72, rel=0.02)

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_finished_upgrade_grants_no_free_production(self, client, session):
        """
        Un chantier termine ne credite rien de plus que le temps ecoule.

        Le rattrapage se faisait en deux morceaux qui se recouvraient, dont l'un
        sur une soustraction a l'envers : un batiment fini peu apres la derniere
        vue offrait pres de vingt-quatre heures de production. La periode
        creditee ne peut pas valoir plus que ce que les niveaux atteints rendent
        sur cette periode.
        """
        territory = self._own_territory(client)
        # De l'energie pour satisfaire le prerequis de l'extracteur.
        territory.add(type=BuildingType.power_station, amount=1)
        session.commit()

        before = territory.resources[ResourceType.iron]

        response = client.post(f'/api/territory/{territory.id}/mater_extractor')
        assert response.status_code == 200

        initial_datetime = datetime.datetime.utcnow()
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(hours=2))
            territory.update_view()

            # Le chantier dure quelques secondes : l'essentiel des deux heures
            # se joue au nouveau niveau, et rien ne peut le depasser.
            ceiling = territory.get_hourly_gain(resource_type=ResourceType.iron) * 2

        assert [b.level for b in territory.buildings
                if b.type == BuildingType.mater_extractor][0] == 1
        credited = territory.resources[ResourceType.iron] - before
        assert credited <= ceiling * 1.01
        assert credited >= ceiling * 0.9

    # ── Habitabilite ────────────────────────────────────────────────────────

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_habitability_drives_food_and_the_population_ceiling(self, client, session):
        """
        Un seul pourcentage, deux effets — et le second n'est pas le premier.

        L'habitabilite multiplie la recolte, puis multiplie a nouveau le nombre
        d'habitants que cette recolte fait vivre. C'est ce qui creuse l'ecart
        entre un monde tempere et un caillou, et ce test dit que les deux
        s'appliquent bien, pas un seul.
        """
        territory = self._own_territory(client)
        territory.add(type=BuildingType.farm, amount=3)
        session.commit()

        # Le monde de depart est tellurique : au-dessus de la reference.
        factor = territory.planet_archetype.habitability_factor
        assert factor > 1.0

        harvest = territory.get_hourly_gain(resource_type=ResourceType.food)
        fed = harvest / FOOD_PER_POPULATION_HOUR
        assert territory.population_capacity == int(fed * factor)

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_settling_a_hostile_world_starts_with_an_outpost(self, client, session):
        """
        On s'installe sur un caillou a la mesure de ce qu'il porte.

        La population de depart est la meme partout, le plafond non : sans
        plafonnement a l'installation, un asteroide serait affame des la
        premiere heure et ingouvernable avant d'avoir servi.
        """
        home = self._own_territory(client)
        rock = Territory.create(
            system_id=home.system_id,
            position_in_system=99,
            archetype='asteroid',
        )
        session.commit()

        rock.assign(user=home.user)
        session.commit()

        assert rock.planet_archetype == PlanetArchetype.asteroid
        assert 0 < rock.population_capacity < 100
        assert rock.population == rock.population_capacity
        assert not rock.is_starving
