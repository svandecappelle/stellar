import datetime
from freezegun import freeze_time
import pytest

from app.models.game.buildings import Building, BuildingType
from app.models.game.fleet import Fleet
from app.models.game.ship import ShipType
from app.models.game.technologies.technology import TechnologyType
from app.models.game.territory import Territory, ResourceType


def my_territory(client):
    """
    Le territoire du joueur.
    ---
    `/api/territories` rend un objet dont `territories` porte la liste, et non
    la liste nue : un territoire appartient a un systeme, qui appartient a une
    galaxie, et la reponse le dit.
    """
    response = client.get('/api/territories')
    assert response.status_code == 200
    territories = response.json['territories']
    assert len(territories) == 1
    return Territory.get(id=territories[0]['id'])


def stock_the_shipyard(territory, session):
    """
    Remplit les soutes du territoire.
    ---
    Un monde de depart n'a rien en caisse hors fer, carbone, silicium et
    credits, et n'extrait ni uranium ni hydrogene ni neutronium. Ce qui est mis
    a l'epreuve ici est l'affectation d'un vaisseau a une flotte, pas la
    conquete des gisements : on donne donc de tout, largement.

    Les bras comptent aussi : une commande coute sa quantite fois le prix
    unitaire, et dix vaisseaux-meres reclament deux cents colons quand la
    colonie en compte cent.
    """
    for resource in ('iron', 'carbon', 'silicium', 'titanium', 'cristal',
                     'uranium', 'hydrogen', 'neutronium', 'credits'):
        setattr(territory, resource, 10000000)
    territory.population = 10000
    session.commit()


def order(client, territory_id, ship_type, quantity, spawn=None):
    body = {"items": [{"type": ship_type.name, "quantity": quantity}]}
    if spawn is not None:
        body["spawn"] = spawn
    response = client.post(f'/api/territory/{territory_id}/ship', json=body)
    assert response.status_code == 200
    return response.json


def unitary_duration(territory, ship_type):
    return ship_type.duration(
        shipyard=Building(
            type=BuildingType.shipyard,
            territory_id=territory.id,
            level=0
        )
    )


class TestShips:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    @pytest.mark.parametrize('item', (
        (s for s in ShipType)
    ))
    def test_create_ships(self, client, session, item):
        territory = my_territory(client)
        stock_the_shipyard(territory, session)

        # Rien en orbite au depart : un monde neuf n'a pas de flotte.
        response = client.get(f'/api/system/{territory.system_id}/fleets')
        assert response.status_code == 200
        assert response.json['fleets'] == []

        events = order(client, territory.id, item, 10)
        duration = unitary_duration(territory, item)

        assert events[0]['eventType'] == 'ship'
        assert events[0]['extraArgs'] == {
            "name": item.name,
            "quantity": 10,
            "initialQuantity": 10,
            "unitaryDuration": duration
        }

        response = client.get('/api/events')
        assert response.status_code == 200
        assert len(response.json.keys()) == 2
        assert len(response.json['general']) == 0
        assert len(response.json['positional']) == 1

        # On part de `lastRefresh` et non de `createdAt` : chaque lecture du
        # territoire repousse ce jalon a l'instant courant, et la lecture des
        # evenements ci-dessus en est une. Compter depuis la creation ferait
        # tomber chaque tranche quelques centiemes sous la duree unitaire, et
        # aucun vaisseau ne sortirait jamais.
        initial_datetime = datetime.datetime.fromisoformat(
            response.json['positional'][0]['extraArgs']['lastRefresh'])

        def check(time_to_wait, expected_remains, expected_built):
            frozen_datetime.tick(datetime.timedelta(seconds=time_to_wait))
            territory.update_view()

            response = client.get('/api/events')
            assert response.status_code == 200
            assert len(response.json['general']) == 0
            assert len(response.json['positional']) == (1 if expected_remains > 0 else 0)

            # Les vaisseaux sortis du chantier sont en orbite, dans une flotte,
            # et non plus poses sur la planete.
            fleets = Fleet.in_orbit_of(territory=territory)
            assert len(fleets) == 1
            assert fleets[0].composition == {item.name: expected_built}

        with freeze_time(initial_datetime) as frozen_datetime:
            check(time_to_wait=duration, expected_remains=9, expected_built=1)
            check(time_to_wait=duration * 5, expected_remains=4, expected_built=6)
            check(time_to_wait=duration, expected_remains=3, expected_built=7)
            check(time_to_wait=duration, expected_remains=2, expected_built=8)
            check(time_to_wait=duration, expected_remains=1, expected_built=9)
            check(time_to_wait=duration, expected_remains=0, expected_built=10)

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_finished_order_delivers_its_whole_balance(self, client, session):
        """
        Une commande retrouvee terminee livre tout son solde.
        ---
        Le joueur peut ne pas revenir avant la fin du chantier. La boucle
        horaire n'a alors rien credite, et c'est l'archivage de l'evenement qui
        livre : il livrait une seule unite pour une commande de dix.
        """
        territory = my_territory(client)
        stock_the_shipyard(territory, session)
        order(client, territory.id, ShipType.Fighter, 10)
        duration = unitary_duration(territory, ShipType.Fighter)

        with freeze_time(datetime.datetime.utcnow() + datetime.timedelta(
                seconds=duration * 10 + 1)):
            territory.update_view()

        fleets = Fleet.in_orbit_of(territory=territory)
        assert len(fleets) == 1
        assert fleets[0].composition == {ShipType.Fighter.name: 10}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_spawn_point_of_the_client_is_kept(self, client, session):
        """
        Le point d'apparition donne par le client est rendu tel quel.
        ---
        Seul Unity connait la geometrie du systeme : le serveur garde ces
        coordonnees sans les interpreter, pour que la flotte se retrouve au
        meme endroit a la prochaine entree dans le systeme.
        """
        territory = my_territory(client)
        stock_the_shipyard(territory, session)
        order(client, territory.id, ShipType.Fighter, 1,
              spawn={"x": 812.5, "y": 0.0, "z": -430.25})
        duration = unitary_duration(territory, ShipType.Fighter)

        with freeze_time(datetime.datetime.utcnow() + datetime.timedelta(
                seconds=duration + 1)):
            territory.update_view()

        fleet = Fleet.in_orbit_of(territory=territory)[0]
        assert fleet.position == {'x': 812.5, 'y': 0.0, 'z': -430.25}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_one_fleet_in_orbit_takes_the_output(self, client, session):
        """Une seule flotte en orbite : elle recoit ce qui sort du chantier."""
        territory = my_territory(client)
        stock_the_shipyard(territory, session)
        existing = Fleet.create(
            system_id=territory.system_id,
            user=territory.user,
            orbiting_territory_id=territory.id,
        )
        session.commit()

        order(client, territory.id, ShipType.Cruiser, 2)
        duration = unitary_duration(territory, ShipType.Cruiser)

        with freeze_time(datetime.datetime.utcnow() + datetime.timedelta(
                seconds=duration * 2 + 1)):
            territory.update_view()

        assert len(Fleet.in_orbit_of(territory=territory)) == 1
        assert existing.composition == {ShipType.Cruiser.name: 2}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_several_fleets_in_orbit_get_a_new_one(self, client, session):
        """
        Plusieurs flottes en orbite : une flotte neuve, et une seule.
        ---
        Le choix ne se tranche pas tout seul, et en designer une au hasard
        reviendrait a decider a la place du joueur. Une seule flotte neuve est
        creee pour toute la commande, memorisee sur l'evenement : sinon dix
        vaisseaux donneraient dix flottes.
        """
        territory = my_territory(client)
        stock_the_shipyard(territory, session)
        for _ in range(2):
            Fleet.create(
                system_id=territory.system_id,
                user=territory.user,
                orbiting_territory_id=territory.id,
            )
        session.commit()

        order(client, territory.id, ShipType.Fighter, 3)
        duration = unitary_duration(territory, ShipType.Fighter)

        now = datetime.datetime.utcnow()
        with freeze_time(now + datetime.timedelta(seconds=duration + 1)):
            territory.update_view()
        with freeze_time(now + datetime.timedelta(seconds=duration * 3 + 1)):
            territory.update_view()

        in_orbit = Fleet.in_orbit_of(territory=territory)
        assert len(in_orbit) == 3
        assert in_orbit[0].is_empty
        assert in_orbit[1].is_empty
        assert in_orbit[2].composition == {ShipType.Fighter.name: 3}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_ships_are_read_from_the_system_not_the_planet(self, client, session):
        """
        Les vaisseaux se lisent par le systeme.
        ---
        `/api/territory/<id>/ships` a disparu avec la notion de vaisseau pose
        sur une planete.
        """
        territory = my_territory(client)
        stock_the_shipyard(territory, session)
        order(client, territory.id, ShipType.Fighter, 1)
        duration = unitary_duration(territory, ShipType.Fighter)

        with freeze_time(datetime.datetime.utcnow() + datetime.timedelta(
                seconds=duration + 1)):
            territory.update_view()

        # 405 et non 404 : le chemin reste appareille par la route generique
        # `POST /api/territory/<id>/<building>`. Ce qui compte est qu'aucune
        # lecture de vaisseaux ne reponde plus ici.
        assert client.get(f'/api/territory/{territory.id}/ships').status_code == 405

        response = client.get(f'/api/system/{territory.system_id}/fleets')
        assert response.status_code == 200
        fleets = response.json['fleets']
        assert len(fleets) == 1
        assert fleets[0]['orbiting_territory_id'] == territory.id
        assert fleets[0]['composition'] == {ShipType.Fighter.name: 1}

        response = client.get(f'/api/system/{territory.system_id}/army')
        assert response.status_code == 200
        assert response.json == {ShipType.Fighter.name: 1}

        # La carte galactique lit tout d'un coup : une question par etoile
        # serait la seule alternative.
        response = client.get('/api/galaxy/Milky%20Way/fleets')
        assert response.status_code == 200
        assert response.json['galaxy'] == 'Milky Way'
        assert len(response.json['fleets']) == 1
        assert response.json['fleets'][0]['system_id'] == territory.system_id
