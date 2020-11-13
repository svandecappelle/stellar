import datetime
from freezegun import freeze_time
import pytest

from app.models.game.buildings import Building, BuildingType
from app.models.game.ship import ShipType
from app.models.game.technologies.technology import TechnologyType
from app.models.game.territory import Territory, ResourceType


class TestShips:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (s for s in ShipType)
    ))
    def test_create_ships(self, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)
        
        response = client.get(
            f'/api/territory/{territory.id}/ships'
        )
        assert response.status_code == 200
        assert len(response.json) == 7
        assert [s['quantity'] for s in response.json] == [0] * 7

        response = client.post(
            f'/api/territory/{territory_id}/ship',
            json={
                "items": [{
                    "type": item.name,
                    "quantity": 10
                }]
            }
        )

        unitary_duration = item.duration(
            shipyard=Building(
                type=BuildingType.shipyard,
                territory_id=territory.id,
                level=0
            )
        )

        assert response.status_code == 200
        assert response.json[0]['eventType'] == 'PositionalEventType.ship'
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

        # increase datetime to simulate future time
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