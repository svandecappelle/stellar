# -*- coding: utf-8 -*-

"""
Le voyage des flottes d'une etoile a l'autre.

Deux choses sont mises a l'epreuve ici, et elles ne se ressemblent pas :

  · le graphe des liaisons, qui doit donner les memes voisins que le client. Le
    serveur ne peut pas verifier cela contre Unity, mais il peut verifier qu'il
    applique bien la regle : cinq voisines au plus dans un rayon de six, un
    rayon qui s'elargit pour les etoiles trop isolees ;
  · le voyage lui-meme, qui n'a pas de boucle de jeu derriere lui. Il avance a
    la lecture, ce qui veut dire que tout se joue sur l'horloge : les tests la
    gelent, comme ceux des chantiers.
"""

import datetime
from freezegun import freeze_time
import pytest

from app.models.game import starlanes
from app.models.game.fleet import Fleet, TRAVEL_SECONDS_PER_UNIT
from app.models.game.system import System


#: Un amas ou toutes les etoiles se voient, et un second trop loin pour lui.
#:
#: Les positions comptent : c'est un rayon de six unites qui decide d'une
#: liaison. Le systeme d'accueil du joueur, pose en « 1_1_1 » par la fixture,
#: appartient au premier amas.
CLUSTER = {
    'A': "0_0_0",
    'B': "4_0_0",
    'C': "8_0_0",
    'D': "12_0_0",
    # Une seconde voisine pour D, sans quoi il n'en aurait qu'une et son rayon
    # s'elargirait jusqu'a rattraper C par un raccourci — le chemin le plus
    # court cesserait alors d'etre unique, et le test ne dirait plus rien.
    'D2': "12_3_0",
}

#: Assez loin pour qu'aucune etoile du premier amas ne l'atteigne, et assez
#: serre pour qu'aucune des siennes n'ait besoin d'elargir sa recherche.
FAR_CLUSTER = {
    'X': "100_0_0",
    'Y': "104_0_0",
    'Z': "102_3_0",
}


def build_clusters(session, galaxy):
    """Pose les deux amas et rend les systemes par nom."""
    systems = {}
    for name, position in list(CLUSTER.items()) + list(FAR_CLUSTER.items()):
        systems[name] = System.create(
            galaxy=galaxy, position=position, create_territories=False)
    session.commit()
    return systems


def home_system(base_universe):
    """Le systeme ou la fixture a installe le joueur."""
    return base_universe["users"][0]['model'].territories[0].system


def user_of(base_universe):
    return base_universe["users"][0]['model']


class TestStarLanes:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_neighbours_follow_the_client_rule(self, session, base_universe):
        """
        Les voisines d'une etoile sont celles que le client relierait.
        ---
        C'est la promesse qui tient tout le reste : une flotte suit les traits
        que le joueur a sous les yeux. Le serveur les recalcule, il ne les
        recoit pas — les deux regles doivent donc rester jumelles.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        galaxy = base_universe["galaxy"].name

        # B voit A et C a quatre unites, et le monde d'accueil a trois : les
        # trois sont dans le rayon, aucun elargissement n'a lieu.
        around_b = starlanes.neighbours(galaxy, systems['B'].id)
        assert systems['A'].id in around_b
        assert systems['C'].id in around_b

        # A et C sont a huit unites l'une de l'autre : au-dela du rayon, donc
        # pas de liaison directe, et un detour par B.
        assert systems['C'].id not in starlanes.neighbours(galaxy, systems['A'].id)

        # L'amas lointain ne se relie a rien du premier : chacune de ses
        # etoiles trouve ses deux voisines chez elle et n'elargit pas.
        around_x = starlanes.neighbours(galaxy, systems['X'].id)
        assert set(around_x) == {systems['Y'].id, systems['Z'].id}

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_route_takes_the_shortest_chain_of_lanes(self, session, base_universe):
        systems = build_clusters(session, base_universe["galaxy"])
        galaxy = base_universe["galaxy"].name
        home = home_system(base_universe)

        path = starlanes.route(galaxy, home.id, systems['D'].id)
        assert path == [home.id, systems['B'].id, systems['C'].id, systems['D'].id]

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_separate_cluster_is_unreachable(self, session, base_universe):
        """
        Deux amas assez serres pour se suffire ne se relient pas.
        ---
        C'est la seule facon d'etre injoignable : une etoile isolee, elle,
        elargit sa recherche jusqu'a trouver deux voisines, si loin soient-elles.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)

        assert starlanes.route(
            base_universe["galaxy"].name, home.id, systems['X'].id) is None


    @pytest.mark.usefixtures("authenticate_as_user")
    def test_lanes_are_published_once_each(self, client, session, base_universe):
        """
        La carte lit le reseau, elle ne le devine pas.
        ---
        La regle de voisinage vit cote serveur et cote client de jeu ; la console
        web n'en a aucune copie. Sans cette route elle ne pourrait ni dessiner
        les liaisons ni justifier un trajet.

        Chaque liaison une seule fois : le graphe interne est reciproque, et la
        rendre deux fois doublerait le poids de la reponse pour un trait qui se
        superpose a lui-meme.
        """
        systems = build_clusters(session, base_universe["galaxy"])

        response = client.get('/api/galaxy/Milky%20Way/lanes')
        assert response.status_code == 200

        lanes = response.json['lanes']
        pairs = [(lane['from'], lane['to']) for lane in lanes]

        assert len(pairs) == len(set(pairs))
        assert all(a < b for a, b in pairs)
        assert all(lane['length'] > 0 for lane in lanes)

        # Le meme reseau que celui qu'empruntent les flottes.
        a, b = systems['A'].id, systems['B'].id
        assert (min(a, b), max(a, b)) in pairs

        # Les deux amas restent separes : aucune liaison ne les relie.
        far = {systems[k].id for k in ('X', 'Y', 'Z')}
        assert not any((p in far) != (q in far) for p, q in pairs)


class TestFleetTravel:

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_fleet_crosses_the_lanes_one_leg_at_a_time(
            self, client, session, base_universe):
        """
        Une flotte franchit les relais l'un apres l'autre.
        ---
        Elle appartient au dernier relais passe : entre deux etoiles, celle
        qu'elle vient de quitter. Le serveur doit pouvoir repondre « dans quel
        systeme ? » a tout instant, et un point du vide n'est pas une reponse.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        departure = datetime.datetime.utcnow()
        with freeze_time(departure):
            response = client.post(
                f'/api/fleet/{fleet.id}/travel',
                json={"system_id": systems['D'].id})

        assert response.status_code == 200
        travel = response.json['travel']
        assert travel['route'] == [
            home.id, systems['B'].id, systems['C'].id, systems['D'].id]
        assert travel['destination_id'] == systems['D'].id
        assert travel['from_id'] == home.id
        assert travel['to_id'] == systems['B'].id

        legs = fleet.legs
        assert len(legs) == 3

        # Au milieu du deuxieme saut : elle a quitte B, elle n'est pas en C.
        elapsed = legs[0] + (legs[1] / 2)
        with freeze_time(departure + datetime.timedelta(seconds=elapsed)):
            response = client.get(f'/api/fleet/{fleet.id}')

        assert response.status_code == 200
        assert response.json['system_id'] == systems['B'].id
        assert response.json['travel']['from_id'] == systems['B'].id
        assert response.json['travel']['to_id'] == systems['C'].id
        assert 0.4 < response.json['travel']['leg_progress'] < 0.6

        # Arrivee : plus de voyage, et le systeme est celui vise.
        with freeze_time(departure + datetime.timedelta(seconds=sum(legs) + 1)):
            response = client.get(f'/api/fleet/{fleet.id}')

        assert response.status_code == 200
        assert response.json['system_id'] == systems['D'].id
        assert response.json['travel'] is None

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_duration_follows_the_distance(self, client, session, base_universe):
        """
        Le temps de vol se paie a la distance parcourue.
        ---
        Sans quoi la topologie ne servirait a rien : un detour de trois sauts
        courts couterait le meme prix qu'un saut long.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        client.post(f'/api/fleet/{fleet.id}/travel',
                    json={"system_id": systems['C'].id})

        lengths = starlanes.leg_lengths(
            base_universe["galaxy"].name,
            [home.id, systems['B'].id, systems['C'].id])

        assert fleet.legs == pytest.approx(
            [length * TRAVEL_SECONDS_PER_UNIT for length in lengths])

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_departing_fleet_leaves_its_orbit(self, client, session, base_universe):
        """
        Partir, c'est quitter l'orbite.
        ---
        Autrement le chantier reste derriere continuerait de lui livrer ses
        vaisseaux a l'autre bout de la galaxie : c'est `orbiting_territory_id`
        qui decide de l'affectation, voir `Fleet.receive_construction`.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        territory = home.territories[0]

        fleet = Fleet.create(
            system_id=home.id,
            user=user_of(base_universe),
            orbiting_territory_id=territory.id)
        session.commit()

        response = client.post(f'/api/fleet/{fleet.id}/travel',
                               json={"system_id": systems['C'].id})
        assert response.status_code == 200
        assert response.json['orbiting_territory_id'] is None
        assert Fleet.in_orbit_of(territory=territory) == []

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_arrived_fleet_is_listed_in_its_new_system(
            self, client, session, base_universe):
        """
        Une flotte arrivee se lit dans le systeme ou elle est.
        ---
        Le piege du rattrapage paresseux : la liste d'un systeme filtre sur
        `system_id`, et une flotte dont le voyage n'a pas encore ete avance
        porte encore l'identifiant de celui qu'elle a quitte. Rattraper apres
        le filtre l'aurait rangee au mauvais endroit — et nulle part, pour qui
        regarde la destination.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        departure = datetime.datetime.utcnow()
        with freeze_time(departure):
            client.post(f'/api/fleet/{fleet.id}/travel',
                        json={"system_id": systems['C'].id})

        arrival = departure + datetime.timedelta(seconds=sum(fleet.legs) + 1)

        with freeze_time(arrival):
            response = client.get(f'/api/system/{systems["C"].id}/fleets')
            assert response.status_code == 200
            assert [f['id'] for f in response.json['fleets']] == [fleet.id]

            response = client.get(f'/api/system/{home.id}/fleets')
            assert response.json['fleets'] == []

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_new_order_in_flight_finishes_the_current_leg(
            self, client, session, base_universe):
        """
        Un ordre donne en vol ne fait pas demi-tour dans le vide.
        ---
        On ne circule que par les liaisons : la flotte finit le saut commence,
        et le nouveau chemin part du relais qu'elle atteint. C'est aussi ce qui
        empeche un ordre repete de faire surplace, chaque ordre repartant
        sinon du meme point.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        departure = datetime.datetime.utcnow()
        with freeze_time(departure):
            client.post(f'/api/fleet/{fleet.id}/travel',
                        json={"system_id": systems['D'].id})

        first_leg = fleet.legs[0]

        # A mi-chemin de B, on la renvoie chez elle.
        with freeze_time(departure + datetime.timedelta(seconds=first_leg / 2)):
            response = client.post(f'/api/fleet/{fleet.id}/travel',
                                   json={"system_id": home.id})

        assert response.status_code == 200
        travel = response.json['travel']

        # Le saut en cours est conserve : elle va toujours vers B, et il lui en
        # reste la moitie.
        assert travel['from_id'] == home.id
        assert travel['to_id'] == systems['B'].id
        assert travel['route'][:2] == [home.id, systems['B'].id]
        assert travel['route'][-1] == home.id
        assert fleet.legs[0] == pytest.approx(first_leg / 2, rel=0.05)

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_travel_to_an_unreachable_cluster_is_refused(
            self, client, session, base_universe):
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        response = client.post(f'/api/fleet/{fleet.id}/travel',
                               json={"system_id": systems['X'].id})
        assert response.status_code == 409

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_travel_to_the_current_system_is_refused(
            self, client, session, base_universe):
        build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        response = client.post(f'/api/fleet/{fleet.id}/travel',
                               json={"system_id": home.id})
        assert response.status_code == 400

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_unknown_system_is_not_found(self, client, session, base_universe):
        """
        Une destination inconnue rend 404, pas une erreur serveur.
        ---
        `System.get` passe par `one()`, qui leve : le detour par une lecture
        qui rend None est ce qui fait la difference entre une reponse et une
        trace de pile.
        """
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        assert client.post(f'/api/fleet/{fleet.id}/travel',
                           json={"system_id": 999999}).status_code == 404
        assert client.post(f'/api/fleet/{fleet.id}/travel',
                           json={}).status_code == 400

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_stopping_puts_the_fleet_at_the_last_node(
            self, client, session, base_universe):
        """
        Interrompre un voyage pose la flotte au dernier relais franchi.
        ---
        Et non la ou elle se trouve : entre deux etoiles elle ne serait dans
        aucun systeme, ce que le modele ne sait pas dire.
        """
        systems = build_clusters(session, base_universe["galaxy"])
        home = home_system(base_universe)
        fleet = Fleet.create(system_id=home.id, user=user_of(base_universe))
        session.commit()

        departure = datetime.datetime.utcnow()
        with freeze_time(departure):
            client.post(f'/api/fleet/{fleet.id}/travel',
                        json={"system_id": systems['D'].id})

        legs = fleet.legs
        halfway = legs[0] + (legs[1] / 2)

        with freeze_time(departure + datetime.timedelta(seconds=halfway)):
            response = client.delete(f'/api/fleet/{fleet.id}/travel')

        assert response.status_code == 200
        assert response.json['travel'] is None
        assert response.json['system_id'] == systems['B'].id

        # Une flotte a l'arret n'a plus rien a interrompre.
        assert client.delete(f'/api/fleet/{fleet.id}/travel').status_code == 400
