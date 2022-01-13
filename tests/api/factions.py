import pytest

from app.models.game.buildings import BuildingType
from app.models.game.technologies.technology_type import TechnologyType
from app.models.game.territory import ResourceType, Territory
from app.models.game.community.faction import Faction


class TestFactions:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_init_factions(self, client, session):
        """
        Test init factions
        ---
        :param client: http client
        :param session: db session
        """
        res = client.post('/api/galaxy/factions')
        assert res.status_code == 200
        assert len(res.json) == 3
        assert len(Faction.all(session=session)) == 3

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_affect_user_faction(self, client, session):
        """
        Test affect faction to user
        :param client: http client
        :param session: db dession
        """
        res = client.post('/api/galaxy/factions')
        assert res.status_code == 200
        res = client.put('/api/faction/1')
        assert res.status_code == 204
        res = client.put('/api/faction/666')
        assert res.status_code == 400
        assert "Faction does not exist" == res.json["message"]
        res = client.put('/api/faction/1')
        assert res.status_code == 409
        assert "User already has a faction" == res.json["message"]

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize("faction", (
        'Technocrats',
        'Warriors',
        'Merchants'
    ))
    def test_check_user_faction_apply_advantages(self, client, session, faction):
        """
        Test affect faction to user
        :param client: http client
        :param session: db dession
        """
        res = client.post('/api/galaxy/factions')
        assert res.status_code == 200
        id = next(f['id'] for f in res.json if f['name'] == faction)
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0].get('id') is not None

        # Check starting resource and set level of building to 1
        territory = Territory.get(id=response.json[0]["id"])
        territory.add(type=BuildingType.power_station, amount=15)
        territory.add(type=BuildingType.mater_extractor, amount=5)
        territory.add(type=BuildingType.economical_center, amount=5)
        territory.add(type=BuildingType.rafinery, amount=5)
        for techno in territory.user.technologies:
            techno.increase(territory=territory, now=True)
        gain_without_faction = {
            ResourceType.mater: territory.get_hourly_gain(ResourceType.mater),
            ResourceType.credits: territory.get_hourly_gain(ResourceType.credits),
            ResourceType.tritium: territory.get_hourly_gain(ResourceType.tritium)
        }
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json) == len(TechnologyType)
        tech_durations = {x['type']: x['duration'] for x in response.json}

        # Apply faction
        res = client.put(f'/api/faction/{id}')
        assert res.status_code == 204
        gain = {
            ResourceType.mater: territory.get_hourly_gain(ResourceType.mater),
            ResourceType.credits: territory.get_hourly_gain(ResourceType.credits),
            ResourceType.tritium: territory.get_hourly_gain(ResourceType.tritium)
        }
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json) == len(TechnologyType)
        new_tech_durations = {x['type']: x['duration'] for x in response.json}
        # Test advantages
        if faction == 'Technocrats':
            resource_bonus = ResourceType.mater
            for tech, duration in tech_durations.items():
                assert new_tech_durations[tech] == duration - (10 / 100 * duration)
        if faction == 'Warriors':
            resource_bonus = ResourceType.tritium
            for tech, duration in tech_durations.items():
                assert new_tech_durations[tech] == duration
        if faction == 'Merchants':
            resource_bonus = ResourceType.credits
            for tech, duration in tech_durations.items():
                assert new_tech_durations[tech] == duration
        expected_gain = gain_without_faction.copy()
        expected_gain[resource_bonus] += expected_gain[resource_bonus] * 1 / 100
        assert gain == expected_gain

        response = client.get(
            '/api/technologies'
        )