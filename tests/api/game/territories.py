import pytest

from app.models.game.technologies.technology import TechnologyType


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
