import datetime
from freezegun import freeze_time
import pytest

from app.models.game.buildings import Building, BuildingType
from app.models.game.ship import ShipType
from app.models.game.technologies.technology import TechnologyType
from app.models.game.territory import Territory, ResourceType


class TestShips:

    @pytest.mark.usefixtures("complexe_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_get_systems(self, client, session):
        response = client.get(
            '/api/galaxy/Milky Way/systems'
        )
        assert response.status_code == 200
        assert len(response.json["systems"]) > 0

        response = client.get(
            f'/api/system/{response.json["systems"][0]["id"]}'
        )
        assert response.status_code == 200

        response = client.get(
            f'/api/system/{response.json["id"]}/territories'
        )
        assert response.status_code == 200
        assert len(response.json["territories"]) > 0

    @pytest.mark.usefixtures("complexe_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_get_my_systems(self, client, session):
        response = client.get(
            '/api/galaxy/Milky Way/systems'
        )
        assert response.status_code == 200
        assert len(response.json["systems"]) == 21

        response = client.get(
            '/api/galaxy/Milky Way/systems?mine=False'
        )
        assert response.status_code == 200
        assert len(response.json["systems"]) == 21

        response = client.get(
            '/api/galaxy/Milky Way/systems?mine=true'
        )
        assert response.status_code == 200
        assert len(response.json["systems"]) == 1