import pytest


class TestGalaxy:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_create_galaxy(self, client, session):
        """
        Test initialize a new galaxy
        ---
        :param client: http client
        :param session: db session
        """
        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 200
        assert response.json['name'] == 'Milky way'

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_create_another_galaxy(self, client, session):
        """
        Test initialize a two different galaxy
        ---
        :param client: http client
        :param session: db session
        """
        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 200
        assert response.json['name'] == 'Milky way'

        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Andromeda'
            }
        )
        assert response.status_code == 200
        assert response.json['name'] == 'Andromeda'


class TestRaisesGalaxy:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_raise_create_galaxy(self, client, session):
        """
        Test cannot initialize a new galaxy because already exists
        ---
        :param client: http client
        :param session: db session
        """
        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 200
        assert response.json['name'] == 'Milky way'
        # Initialisation of the same galaxy
        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 400

    @pytest.mark.usefixtures()
    def test_raise_not_allowed_create_galaxy(self, client, session):
        """
        Test cannot initialize a new galaxy because not authenticated
        ---
        :param client: http client
        :param session: db session
        """
        response = client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 401
