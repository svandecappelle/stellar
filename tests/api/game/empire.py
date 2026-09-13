# -*- coding: utf-8 -*-

"""
La vue d'empire : tous les mondes d'une galaxie en une lecture.

Ce que la route doit garantir, et que /api/galaxy/<name>/territories ne
garantit pas : des ressources RATTRAPEES — c'est sur elles que le joueur decide
une depense —, les defenses posees, les chantiers en cours et ce qui tient
l'orbite.
"""

import pytest

from app.models.audit import Action, AuditLog
from app.models.game.buildings import BuildingType
from app.models.game.defense import DefenseType
from app.models.game.fleet import Fleet
from app.models.game.galaxy import Galaxy
from app.models.game.ship import ShipType
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import TechnologyType
from app.models.game.territory import ResourceType, Territory
from app.models.role import RoleType
from app.models.user import User


class TestEmpire:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_empire_lists_worlds_with_buildings(self, client, base_universe):
        response = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire'
        )
        assert response.status_code == 200
        assert response.json['galaxy_name'] == base_universe["galaxy"].name

        worlds = response.json['worlds']
        assert len(worlds) == 1

        world = worlds[0]
        assert world['id'] is not None
        # Les batiments viennent avec leur niveau, leur cout et leur duree : la
        # vue dessine un bouton « Upgrade » a partir d'eux, elle n'a rien a
        # aller rechercher monde par monde.
        assert set(world['buildings']) == {b.name for b in BuildingType}
        assert world['buildings'][BuildingType.power_station.name]['level'] == 0
        assert 'cost' in world['buildings'][BuildingType.power_station.name]
        # Et les trois blocs que la liste de territoires ne porte pas. Les
        # batteries existent des la colonisation, a zero piece : c'est la
        # quantite qui dit ce qui est pose, pas la presence de la ligne.
        assert {d['type'] for d in world['defenses']} == {d.name for d in DefenseType}
        assert all(d['quantity'] == 0 for d in world['defenses'])
        assert world['events'] == []
        assert world['orbit'] == {}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_empire_carries_defenses_and_orbit(self, client, session, base_universe):
        territory = base_universe["users"][0]['model'].territories[0]
        territory.add(type=DefenseType.FlackCannon, amount=4)

        fleet = Fleet.create(
            system_id=territory.system_id,
            user=territory.user,
            orbiting_territory_id=territory.id,
        )
        fleet.add_ships(ship_type=ShipType.Fighter, amount=3)
        session.commit()

        response = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire'
        )
        assert response.status_code == 200

        world = response.json['worlds'][0]
        posed = {d['type']: d['quantity'] for d in world['defenses']}
        assert posed[DefenseType.FlackCannon.name] == 4
        assert world['orbit'] == {ShipType.Fighter.name: 3}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_empire_catches_worlds_up(self, client, session, base_universe):
        """
        Les ressources sont creditees avant d'etre rendues.
        ---
        C'est la raison d'etre de la route : une vue d'empire qui listerait les
        stocks tels que la base les porte afficherait ceux de la derniere
        visite, et refuserait des constructions que le monde peut payer.
        """
        territory = base_universe["users"][0]['model'].territories[0]
        territory.add(type=BuildingType.mater_extractor, amount=5)
        session.commit()

        before = Territory.get(id=territory.id).resources[ResourceType.iron]

        response = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire'
        )
        assert response.status_code == 200
        assert response.json['worlds'][0]['resources']['iron'] > before

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_empire_refuses_unknown_galaxy(self, client):
        response = client.post('/api/galaxy/Nowhere/empire')
        assert response.status_code == 404

    @pytest.mark.usefixtures("base_universe")
    def test_empire_needs_a_session(self, client, base_universe):
        response = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire'
        )
        assert response.status_code == 401


class TestModeration:
    """
    L'empire d'un autre joueur, et les gestes gratuits qu'un arbitre y pose.

    Ce qui se joue ici tient en une phrase : la portee. Un moderateur arbitre
    UNE partie, et son droit s'arrete a sa galaxie ; un joueur ordinaire n'a
    aucun droit sur l'empire d'un autre, meme en lecture.
    """

    def _arbitre(self, session, client, scope="Milky Way", role=RoleType.moderator):
        user = User.new(username="arbitre", password="un-mot-de-passe",
                        email="arbitre@testing.com")
        if role is not None:
            user.add_role(role, scope=scope)
        session.commit()
        assert client.post('/api/auth/login', json={
            "username": "arbitre", "password": "un-mot-de-passe"}).status_code == 200
        return user

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_player_reads_only_his_own_empire(self, client, base_universe):
        answer = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire',
            json={"player": "arbitre-inexistant"})
        assert answer.status_code == 403

        # Et sa propre lecture dit qu'il n'arbitre rien : c'est ce drapeau qui
        # decide de tout ce que la console propose.
        answer = client.post(f'/api/galaxy/{base_universe["galaxy"].name}/empire')
        assert answer.status_code == 200
        assert answer.json['player'] == "user"
        assert answer.json['moderating'] is False
        assert answer.json['can_moderate'] is False

    @pytest.mark.usefixtures("base_universe")
    def test_a_moderator_reads_another_empire(self, client, session, base_universe):
        self._arbitre(session, client)

        answer = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire',
            json={"player": "user"})
        assert answer.status_code == 200
        assert answer.json['player'] == "user"
        assert answer.json['moderating'] is True
        assert answer.json['can_moderate'] is True
        assert len(answer.json['worlds']) == 1

        # Le bloc de tenue est celui du PROPRIETAIRE : un arbitre doit voir
        # venir la secession qu'on vient lui signaler, la ou un joueur tiers
        # n'apprendrait rien du reseau d'un autre.
        assert answer.json['worlds'][0]['holding'] is not None
        assert answer.json['worlds'][0]['holding']['owned'] is True

    @pytest.mark.usefixtures("base_universe")
    def test_moderation_stops_at_the_galaxy(self, client, session, base_universe):
        """Moderateur d'ailleurs : aucun droit ici."""
        self._arbitre(session, client, scope="Andromeda")

        assert client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire',
            json={"player": "user"}).status_code == 403
        assert client.get(
            f'/api/galaxy/{base_universe["galaxy"].name}/players').status_code == 403

    @pytest.mark.usefixtures("base_universe")
    def test_an_administrator_moderates_every_galaxy(self, client, session, base_universe):
        """La portee d'un administrateur est '*' : elle vaut partout."""
        self._arbitre(session, client, scope="*", role=RoleType.admin)

        answer = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire',
            json={"player": "user"})
        assert answer.status_code == 200
        assert answer.json['moderating'] is True

    @pytest.mark.usefixtures("base_universe")
    def test_an_unknown_player_is_not_found(self, client, session, base_universe):
        self._arbitre(session, client)
        assert client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/empire',
            json={"player": "personne"}).status_code == 404

    @pytest.mark.usefixtures("base_universe")
    def test_the_player_list_names_who_holds_something(self, client, session, base_universe):
        self._arbitre(session, client)

        answer = client.get(f'/api/galaxy/{base_universe["galaxy"].name}/players')
        assert answer.status_code == 200
        # L'arbitre ne tient rien : il ne figure donc pas dans la liste.
        assert answer.json['players'] == [{'username': 'user', 'worlds': 1}]

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_is_instant_and_free(self, client, session, base_universe):
        territory = base_universe["users"][0]['model'].territories[0]
        before = dict(territory.resources)
        self._arbitre(session, client)

        answer = client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "building",
            "name": BuildingType.power_station.name,
            "amount": 3,
        })
        assert answer.status_code == 200

        world = answer.json
        # Pose tout de suite : le niveau est la, et aucun chantier ne court.
        assert world['buildings'][BuildingType.power_station.name]['level'] == 3
        assert world['events'] == []
        # Et sans rien prendre : les reserves n'ont pas baisse.
        fresh = Territory.get(id=territory.id)
        for resource, amount in before.items():
            if resource == ResourceType.energy:
                continue  # calculee depuis les batiments, elle monte justement
            assert fresh.resources[resource] >= amount

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_is_written_to_the_journal(self, client, session, base_universe):
        territory = base_universe["users"][0]['model'].territories[0]
        self._arbitre(session, client)

        assert client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "defense",
            "name": DefenseType.FlackCannon.name,
            "amount": 12,
        }).status_code == 200

        line = (session.query(AuditLog)
                .filter(AuditLog.action == Action.MODERATION_GRANT)
                .one())
        assert line.username == "arbitre"
        # `details` est range en JSON : c'est `serialize` qui le relit.
        details = line.serialize['details']
        assert details['target'] == "user"
        assert details['element'] == DefenseType.FlackCannon.name
        assert details['applied'] == 12

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_can_take_back(self, client, session, base_universe):
        territory = base_universe["users"][0]['model'].territories[0]
        territory.add(type=DefenseType.FlackCannon, amount=4)
        session.commit()
        self._arbitre(session, client)

        # Plus que ce qui est pose : on retire ce qui est pose, sans creuser.
        answer = client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "defense",
            "name": DefenseType.FlackCannon.name,
            "amount": -10,
        })
        assert answer.status_code == 200
        posed = {d['type']: d['quantity'] for d in answer.json['defenses']}
        assert posed[DefenseType.FlackCannon.name] == 0

    @pytest.mark.usefixtures("base_universe")
    def test_a_granted_ship_joins_a_fleet_in_orbit(self, client, session, base_universe):
        """Un vaisseau n'est jamais sur la planete : il appartient a une flotte."""
        territory = base_universe["users"][0]['model'].territories[0]
        self._arbitre(session, client)

        answer = client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "ship",
            "name": ShipType.Fighter.name,
            "amount": 5,
        })
        assert answer.status_code == 200
        assert answer.json['orbit'] == {ShipType.Fighter.name: 5}

        fleets = Fleet.in_orbit_of(territory=Territory.get(id=territory.id),
                                   user=base_universe["users"][0]['model'])
        assert len(fleets) == 1

    @pytest.mark.usefixtures("base_universe")
    def test_the_rule_of_place_still_holds(self, client, session, base_universe):
        """
        Un arbitre se passe du prix, du delai et des technologies. Pas du sol :
        un craqueur sur un monde sans hydrogene ne craquerait rien, et le monde
        mentirait a son proprietaire.
        """
        territory = base_universe["users"][0]['model'].territories[0]
        self._arbitre(session, client)

        answer = client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "building",
            "name": BuildingType.gas_cracker.name,
            "amount": 1,
        })
        assert answer.status_code == 400
        assert 'hydrogen' in answer.json['message']

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_refuses_nonsense(self, client, session, base_universe):
        territory = base_universe["users"][0]['model'].territories[0]
        self._arbitre(session, client)
        route = f'/api/territory/{territory.id}/grant'

        assert client.post(route, json={"kind": "sandwich", "name": "x",
                                        "amount": 1}).status_code == 400
        assert client.post(route, json={"kind": "building", "name": "chateau",
                                        "amount": 1}).status_code == 400
        assert client.post(route, json={"kind": "building",
                                        "name": BuildingType.farm.name,
                                        "amount": 0}).status_code == 400
        assert client.post(route, json={"kind": "building",
                                        "name": BuildingType.farm.name,
                                        "amount": 99999}).status_code == 400

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_player_cannot_grant_himself_anything(self, client, base_universe):
        """Le droit ne vient pas de la propriete : c'est tout le sujet."""
        territory = base_universe["users"][0]['model'].territories[0]

        assert client.post(f'/api/territory/{territory.id}/grant', json={
            "kind": "building",
            "name": BuildingType.farm.name,
            "amount": 5,
        }).status_code == 403


class TestResearchModeration:
    """
    L'arbre d'un joueur, ouvert et corrige par un arbitre.

    Deux choses s'y jouent que l'empire ne posait pas : la recherche ne pend a
    aucun monde — elle suit le joueur dans toutes ses galaxies —, et un niveau
    a un plafond.
    """

    def _arbitre(self, session, client, scope="Milky Way", role=RoleType.moderator):
        user = User.new(username="arbitre", password="un-mot-de-passe",
                        email="arbitre@testing.com")
        if role is not None:
            user.add_role(role, scope=scope)
        session.commit()
        assert client.post('/api/auth/login', json={
            "username": "arbitre", "password": "un-mot-de-passe"}).status_code == 200
        return user

    def _node(self, payload, name):
        return next(t for t in payload['technologies'] if t['type'] == name)

    @pytest.mark.usefixtures("base_universe")
    def test_a_moderator_reads_another_tree(self, client, session, base_universe):
        self._arbitre(session, client)

        answer = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/research',
            json={"player": "user"})
        assert answer.status_code == 200
        assert answer.json['player'] == "user"
        assert answer.json['moderating'] is True
        assert answer.json['can_moderate'] is True
        # La meme charge utile que ce que le joueur lit : un arbitre qui lirait
        # autre chose arbitrerait sur autre chose.
        mine = client.get('/api/technologies').json
        assert set(answer.json) >= set(mine)
        assert len(answer.json['technologies']) == len(mine['technologies'])

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_player_reads_only_his_own_tree(self, client, base_universe):
        answer = client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/research',
            json={"player": "quelqu-un-d-autre"})
        assert answer.status_code == 403

        answer = client.post(f'/api/galaxy/{base_universe["galaxy"].name}/research')
        assert answer.status_code == 200
        assert answer.json['moderating'] is False

    @pytest.mark.usefixtures("base_universe")
    def test_a_granted_level_is_instant_and_free(self, client, session, base_universe):
        player = base_universe["users"][0]['model']
        self._arbitre(session, client)
        galaxy = base_universe["galaxy"].name

        before = client.post(f'/api/galaxy/{galaxy}/research',
                             json={"player": "user"}).json['research']

        answer = client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 3})
        assert answer.status_code == 200
        assert answer.json['applied'] == 3
        assert self._node(answer.json, 'alliages')['level'] == 3
        # Ni reserve entamee, ni emplacement occupe, ni chantier ouvert.
        assert answer.json['research'] == before
        assert answer.json['used_slots'] == 0
        assert answer.json['pending'] == []

        session.expire_all()
        assert Technology.get(user=player, type=TechnologyType.alliages).level == 3

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_stops_at_the_ceiling(self, client, session, base_universe):
        self._arbitre(session, client)
        galaxy = base_universe["galaxy"].name

        answer = client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 999})
        assert answer.status_code == 200

        node = self._node(answer.json, 'alliages')
        assert node['level'] == node['max_level']
        assert answer.json['applied'] == node['max_level']
        # Et un second coup ne franchit plus rien.
        again = client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 5})
        assert again.json['applied'] == 0

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_can_take_back(self, client, session, base_universe):
        self._arbitre(session, client)
        galaxy = base_universe["galaxy"].name

        client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 2})
        answer = client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": -9})
        assert answer.status_code == 200
        assert answer.json['applied'] == -2
        assert self._node(answer.json, 'alliages')['level'] == 0

    @pytest.mark.usefixtures("base_universe")
    def test_the_journal_names_the_technology(self, client, session, base_universe):
        self._arbitre(session, client)
        galaxy = base_universe["galaxy"].name

        client.post(f'/api/galaxy/{galaxy}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 1})

        line = (session.query(AuditLog)
                .filter(AuditLog.action == Action.MODERATION_GRANT)
                .one())
        details = line.serialize['details']
        assert line.username == "arbitre"
        assert details['kind'] == 'technology'
        assert details['element'] == 'alliages'
        assert details['target'] == "user"

    @pytest.mark.usefixtures("base_universe")
    def test_the_right_is_anchored_in_a_galaxy(self, client, session, base_universe):
        """
        Une technologie suit le joueur partout : moderer une partie ou il ne
        tient rien ne donne pas barre sur son empire d'ailleurs.
        """
        self._arbitre(session, client, scope="Andromeda")
        galaxy = Galaxy.create(session=session, name="Andromeda")
        session.commit()

        assert client.post(f'/api/galaxy/{galaxy.name}/research/grant', json={
            "player": "user", "name": "alliages", "amount": 1}).status_code == 400

    @pytest.mark.usefixtures("base_universe")
    def test_a_grant_refuses_nonsense(self, client, session, base_universe):
        self._arbitre(session, client)
        route = f'/api/galaxy/{base_universe["galaxy"].name}/research/grant'

        assert client.post(route, json={"player": "user", "name": "chateau",
                                        "amount": 1}).status_code == 404
        assert client.post(route, json={"player": "user", "name": "alliages",
                                        "amount": 0}).status_code == 400
        assert client.post(route, json={"name": "alliages",
                                        "amount": 1}).status_code == 400

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_player_cannot_grant_himself_a_level(self, client, base_universe):
        assert client.post(
            f'/api/galaxy/{base_universe["galaxy"].name}/research/grant',
            json={"player": "user", "name": "alliages", "amount": 5}
        ).status_code == 403


class TestArbitratingOneSelf:
    """
    Un moderateur arbitre-t-il son propre empire ?

    Oui, mais jamais par megarde : sans nom dans le corps il JOUE, avec son
    propre nom il arbitre. Les routes de geste, elles, n'ont jamais regarde que
    le droit de moderer la galaxie — refuser ici ce qu'elles acceptent la-bas
    aurait fait deux regles pour une meme question.
    """

    def _arbitre_avec_un_monde(self, session, client, base_universe):
        user = User.new(username="arbitre", password="un-mot-de-passe",
                        email="arbitre@testing.com")
        user.add_role(RoleType.moderator, scope="Milky Way")
        # Un systeme a lui, pour qu'il ait un empire a arbitrer : celui du
        # joueur n'a pas toujours de monde libre, leur nombre etant tire au sort.
        from app.models.game.system import System
        system = System.create(galaxy=base_universe["galaxy"], position="9_9_9")
        system.territories[0].assign(user=user)
        session.commit()
        assert client.post('/api/auth/login', json={
            "username": "arbitre", "password": "un-mot-de-passe"}).status_code == 200
        return user

    @pytest.mark.usefixtures("base_universe")
    def test_without_a_name_he_plays(self, client, session, base_universe):
        self._arbitre_avec_un_monde(session, client, base_universe)

        answer = client.post(f'/api/galaxy/{base_universe["galaxy"].name}/empire')
        assert answer.status_code == 200
        assert answer.json['player'] == "arbitre"
        assert answer.json['moderating'] is False
        assert answer.json['can_moderate'] is True

    @pytest.mark.usefixtures("base_universe")
    def test_with_his_own_name_he_arbitrates(self, client, session, base_universe):
        self._arbitre_avec_un_monde(session, client, base_universe)

        answer = client.post(f'/api/galaxy/{base_universe["galaxy"].name}/empire',
                             json={"player": "arbitre"})
        assert answer.status_code == 200
        assert answer.json['moderating'] is True

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_plain_player_naming_himself_simply_plays(self, client, base_universe):
        """Lire son empire ne peut pas dependre de la facon dont on le demande."""
        answer = client.post(f'/api/galaxy/{base_universe["galaxy"].name}/empire',
                             json={"player": "user"})
        assert answer.status_code == 200
        assert answer.json['moderating'] is False
