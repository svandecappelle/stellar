import pytest

from app.models.game.buildings import BuildingType
from app.models.game.technologies.technology import TechnologyType
from app.models.game.territory import Territory, ResourceType


class TestEvents:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_new_basic_event(self, client, session):
        """
        Test user event
        ---
        :param client: http client
        :param session: db session
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
            f'/api/technology/computer/{response.json[0]["id"]}'
        )
        assert response.status_code == 200
        assert response.json['eventType'] == 'PositionalEventType.technology'
        assert response.json['extraArgs'] == {
            'type': 'computer'
        }

        # Check tech is not yet completed
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json) == len(TechnologyType)
        assert list(map(lambda x: x['level'], response.json)) == [0] * len(TechnologyType)

        # Check event is created
        response = client.get(
            '/api/technologies/events'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
