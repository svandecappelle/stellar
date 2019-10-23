import pytest


class TestGalaxy:

    def test_create_galaxy(self, http_client):
        """
        """
        response = http_client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )

        assert response.status_code == 200
        assert response.json['name'] == 'Milky way'


class TestRaisesGalaxy:

    def test_create_galaxy(self, http_client):
        """
        """
        response = http_client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )

        assert response.status_code == 200
        assert response.json['name'] == 'Milky way'

        # Reinit
        response = http_client.post(
            '/api/galaxy/create',
            json={
                'name': 'Milky way'
            }
        )
        assert response.status_code == 400
