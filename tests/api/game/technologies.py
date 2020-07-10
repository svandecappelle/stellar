import pytest

from app.models.game.technologies.technology import TechnologyType


class TestTechnologies:

    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.usefixtures("base_universe")
    def test_new_user_basis_technologies(self, client, session):
        """
        Test initialize a new galaxy
        ---
        :param client: http client
        :param session: db session
        """
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json) == len(TechnologyType)
        assert list(map(lambda x: x['level'], response.json)) == [0] * len(TechnologyType)
