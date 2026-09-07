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
        assert len(response.json['territories']) == 1
        territory_id = response.json['territories'][0].get('id')
        assert territory_id is not None

        # `computer` coute du cristal. Un monde tellurique en extrait, mais il
        # n'en a rien en caisse a l'instant zero et on commande tout de suite :
        # sans ce ravitaillement la recherche part en 400. Ce qui est mis a
        # l'epreuve ici est la creation de l'evenement, pas le cout.
        territory = Territory.get(id=territory_id)
        territory.add(type=ResourceType.cristal, amount=300000)
        session.commit()

        # Add event using increase a tech
        response = client.post(
            f'/api/technology/computer/{territory_id}'
        )
        assert response.status_code == 200
        assert response.json['eventType'] == 'technology'
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
