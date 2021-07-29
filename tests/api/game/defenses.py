import datetime
from freezegun import freeze_time
import pytest

from app.models.game.buildings import Building, BuildingType
from app.models.game.defense import DefenseType
from app.models.game.technologies.technology import Technology, TechnologyType
from app.models.game.territory import Territory, ResourceType


class TestDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (d for d in DefenseType)
    ))
    def test_create_defense(self, base_universe, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)


        if item == DefenseType.Shield:
            # required for shield
            me = base_universe[0]['model']
            technology = Technology.get(user=me, type=TechnologyType.energy).level = 8
            territory.add(type=ResourceType.credits, amount=300000)
            territory.add(type=ResourceType.mater, amount=300000)
            territory.add(type=ResourceType.tritium, amount=300000)
            # increase energy
            territory.add(type=BuildingType.power_station, amount=10)
            territory.add(type=ResourceType.population, amount=200)
            session.commit()

        unitary_duration = item.duration(
            factory=Building(
                type=BuildingType.shipyard,
                territory_id=territory.id,
                level=0
            )
        )

        response = client.post(
            f'/api/territory/{territory_id}/defense',
            json={
                "items": [{
                    "type": item.name,
                    "quantity": 10
                }]
            }
        )
        assert response.status_code == 200
        assert response.json[0]['eventType'] == 'PositionalEventType.defense'
        assert response.json[0]['extraArgs'] == {
            "name": item.name,
            "quantity": 10,
            "initialQuantity": 10,
            "unitaryDuration": unitary_duration
        }


        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # set datetime to simulate time at event creation
        initial_datetime = datetime.datetime.fromisoformat(response.json['positional'][0]['createdAt'])

        def check(time_to_wait, expected_remains):
            frozen_datetime.tick(datetime.timedelta(seconds=time_to_wait))
            territory.update_view()

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == (1 if expected_remains > 0 else 0)

        # some of them created
        with freeze_time(initial_datetime) as frozen_datetime:
            # create one
            check(time_to_wait=unitary_duration, expected_remains=9)
            check(time_to_wait=unitary_duration * 5, expected_remains=4)
            check(time_to_wait=unitary_duration, expected_remains=3)
            check(time_to_wait=unitary_duration, expected_remains=2)
            check(time_to_wait=unitary_duration, expected_remains=1)
            check(time_to_wait=unitary_duration, expected_remains=0)


class TestRaiseDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (d for d in DefenseType)
    ))
    def test_raise_create_defense_prerequisite(self, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)
        # 
        territory.mater = 0
        session.commit()

        response = client.post(
            f'/api/territory/{territory_id}/defense',
            json={
                "items": [{
                    "type": item.name,
                    "quantity": 10
                }]
            }
        )
        assert response.status_code == 400
        assert response.json["message"] == f"Cannot build 10 {item.name}. Prerequisites not reached."


        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 0
