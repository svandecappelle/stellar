import datetime
from freezegun import freeze_time
import pytest

from app.models.game.defenses.defense import DefenseType
from app.models.game.technologies.technology import TechnologyType
from app.models.game.territory import Territory, ResourceType


class TestDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (DefenseType.FlackCannon),
        (DefenseType.MissileBattery)
    ))
    def test_create_defense(self, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
        territory_id = response.json[0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)

        response = client.post(
            f'/api/territory/{territory_id}/defense/{item}',
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
            "unitaryDuration": 0.8
        }


        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # increase datetime to simulate future time
        initial_datetime = datetime.datetime.utcnow()

        # some of them created
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(seconds=3))
            territory.update_view()

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == 1

        # all finished
        with freeze_time(initial_datetime) as frozen_datetime:
            frozen_datetime.tick(datetime.timedelta(seconds=10))
            territory.update_view()

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == 0


class TestRaiseDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (DefenseType.FlackCannon),
        (DefenseType.MissileBattery)
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
            f'/api/territory/{territory_id}/defense/{item}',
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
