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

        # `Architecture de calcul` se paie en Donnees, en silicium et en
        # credits. Les Donnees viennent de la reserve du joueur — l'academie les
        # produit, et il n'y en a aucune a l'instant zero. Ce qui est mis a
        # l'epreuve ici est la creation de l'evenement, pas le cout.
        territory = Territory.get(id=territory_id)
        territory.add(type=ResourceType.silicium, amount=300000)
        territory.add(type=ResourceType.credits, amount=300000)
        territory.user.add_research(300000)
        session.commit()

        # Add event using increase a tech. Plus de territoire dans le chemin :
        # la recherche appartient au joueur et se paie sur tout son empire.
        response = client.post('/api/technology/calcul')
        assert response.status_code == 200
        assert response.json['eventType'] == 'research'
        assert response.json['extraArgs']['type'] == 'calcul'
        assert response.json['extraArgs']['level'] == 1

        # Check tech is not yet completed
        response = client.get(
            '/api/technologies'
        )
        assert response.status_code == 200
        assert len(response.json['technologies']) == len(TechnologyType)
        assert [t['level'] for t in response.json['technologies']] ==             [0] * len(TechnologyType)
        assert response.json['used_slots'] == 1

        # Check event is created
        response = client.get(
            '/api/technologies/events'
        )
        assert response.status_code == 200
        assert len(response.json) == 1
