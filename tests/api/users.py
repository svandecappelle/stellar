import pytest


class TestGalaxy:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_create_galaxy(self, client, session):
        """
        Check if user can be retrieve
        ---
        :param client:
        :param session:
        :return:
        """
        response = client.get("/api/user/admin")
        assert response.status_code == 200
        assert response.json['username'] == "admin"
