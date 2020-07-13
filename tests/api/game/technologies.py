import pytest

from app.models.game.technologies.technology import TechnologyType


class TestTechnologies:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_new_user_basis_technologies(self, client):
        """
        Test initialize a new galaxy
        ---
        :param client: http client
        """
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json) == len(TechnologyType)
        assert list(map(lambda x: x['level'], response.json)) == [0] * len(TechnologyType)
