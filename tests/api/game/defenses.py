import datetime
from freezegun import freeze_time
import pytest

from app.models.game.buildings import Building, BuildingType
from app.models.game.defense import DefenseType
from app.models.game.territory import Territory, ResourceType


class TestDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (d for d in DefenseType)
    ))
    def test_create_defense(self, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json['territories']) == 1
        territory_id = response.json['territories'][0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)


        # On remplit les soutes pour toutes les pieces, pas seulement le
        # bouclier. Un monde tellurique extrait bien du titane et du cristal,
        # mais il en a zero en caisse a l'instant zero, et pas une goutte
        # d'uranium jamais : le bloc reserve au Shield laissait donc le laser,
        # l'artillerie ionique et le coilgun tomber en 400, puisqu'on commande
        # avant que la production ait tourne une seule seconde. Ce qui est mis a
        # l'epreuve ici est la mise en chantier et son egrenage dans le temps,
        # pas l'approvisionnement.
        #
        # Rien a faire du cote des technologies : le `requirements` des pieces
        # n'est lu que par l'interface, le serveur ne le verifie nulle part.
        territory.add(type=ResourceType.credits, amount=300000)
        territory.add(type=ResourceType.tritium, amount=300000)
        for material in ResourceType.materials():
            territory.add(type=material, amount=300000)
        # De l'energie et des bras pour les servir, a la mesure de la commande :
        # une piece coute sa quantite fois le prix unitaire, et dix boucliers
        # tirent mille sur le reseau.
        territory.add(type=BuildingType.power_station, amount=15)
        territory.add(type=ResourceType.population, amount=200)
        session.commit()

        unitary_duration = item.duration(
            shipyard=Building(
                type=BuildingType.shipyard,
                territory_id=territory.id,
                level=0
            )
        )

        response = client.post(
            f'/api/territory/{territory_id}/defense',
            json={
                "items": [{
                    "type": item.name,
                    "quantity": 10
                }]
            }
        )
        assert response.status_code == 200
        assert response.json[0]['eventType'] == 'defense'
        assert response.json[0]['extraArgs'] == {
            "name": item.name,
            "quantity": 10,
            "initialQuantity": 10,
            "unitaryDuration": unitary_duration
        }


        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # set datetime to simulate time at event creation
        initial_datetime = datetime.datetime.fromisoformat(response.json['positional'][0]['createdAt'])

        def check(time_to_wait, expected_remains):
            frozen_datetime.tick(datetime.timedelta(seconds=time_to_wait))
            territory.update_view()

            # check event is finished between previous state
            # And if building has been increased
            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json.keys()) == 2
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == (1 if expected_remains > 0 else 0)

        # some of them created
        with freeze_time(initial_datetime) as frozen_datetime:
            # create one
            check(time_to_wait=unitary_duration, expected_remains=9)
            check(time_to_wait=unitary_duration * 5, expected_remains=4)
            check(time_to_wait=unitary_duration, expected_remains=3)
            check(time_to_wait=unitary_duration, expected_remains=2)
            check(time_to_wait=unitary_duration, expected_remains=1)
            check(time_to_wait=unitary_duration, expected_remains=0)


class TestRaiseDefenses:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (d for d in DefenseType)
    ))
    def test_raise_create_defense_prerequisite(self, client, session, item):
        response = client.get(
            '/api/territories'
        )
        assert response.status_code == 200
        assert len(response.json['territories']) == 1
        territory_id = response.json['territories'][0].get('id')
        assert territory_id is not None
        territory = Territory.get(id=territory_id)
        # 
        territory.iron = 0
        session.commit()

        response = client.post(
            f'/api/territory/{territory_id}/defense',
            json={
                "items": [{
                    "type": item.name,
                    "quantity": 10
                }]
            }
        )
        assert response.status_code == 400
        assert response.json["message"] == f"Cannot build 10 {item.name}. Prerequisites not reached."


        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 0


class TestDefenseOrderCost:
    """
    Ce qu'une commande coute, et quand elle le coute.
    """

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_order_costs_its_quantity_not_one_piece(self, client, session):
        """
        Dix pieces coutent dix fois le prix d'une.
        ---
        La verification portait sur `element.cost`, qui est unitaire : une
        commande de dix passait avec de quoi n'en payer qu'une seule — ce que
        le message de refus dementait deja, puisqu'il annonce la quantite.
        """
        response = client.get('/api/territories')
        assert response.status_code == 200
        territory = Territory.get(id=response.json['territories'][0]["id"])

        unit = DefenseType.FlackCannon.cost
        stock = territory.resources[ResourceType.iron]
        # Le monde de depart tient trois canons, pas dix.
        assert 3 * unit['iron'] <= stock < 10 * unit['iron']

        def order(quantity):
            return client.post(
                f'/api/territory/{territory.id}/defense',
                json={"items": [{"type": DefenseType.FlackCannon.name,
                                 "quantity": quantity}]}
            )

        response = order(10)
        assert response.status_code == 400
        assert response.json["message"] == (
            "Cannot build 10 FlackCannon. Prerequisites not reached.")

        # Temps fige : la production creditee par la vue se melerait sinon a la
        # facture.
        with freeze_time(datetime.datetime.utcnow()):
            before = territory.resources[ResourceType.iron]
            assert order(3).status_code == 200
            assert territory.resources[ResourceType.iron] == pytest.approx(
                before - 3 * unit['iron'])
