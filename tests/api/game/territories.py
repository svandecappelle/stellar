import datetime

import pytest

from freezegun import freeze_time

from app.models.game.buildings import BuildingType
from app.models.game.territory import ResourceType, Territory


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
        (ResourceType.mater, 10000),
        (ResourceType.credits, 8000),
        (ResourceType.population, 100),
        (ResourceType.tritium, 100),
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
        (ResourceType.mater, 10000, BuildingType.mater_extractor),
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
            (ResourceType.mater, 10000, BuildingType.mater_extractor),
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
