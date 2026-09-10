# -*- coding: utf-8 -*-

"""
L'API de la recherche, de bout en bout.

Ce que les tests de regles (`tests/unit/research.py`) ne peuvent pas couvrir :
tout ce qui passe par la base. Les recherches en cours, les emplacements
occupes, l'encaissement d'un niveau arrive a terme, l'annulation et son
remboursement — autant de choses qui n'existent que dans une session.
"""

import datetime

from freezegun import freeze_time
import pytest

from app.models.game.buildings import BuildingType
from app.models.game.technologies.technology import Technology
from app.models.game.technologies.technology_type import (
    Branch, TechnologyType)
from app.models.game.territory import Territory, ResourceType


def my_territory(client):
    response = client.get('/api/territories')
    assert response.status_code == 200
    return Territory.get(id=response.json['territories'][0]['id'])


def bankroll(territory, session, data=500000):
    """
    De quoi payer n'importe quel premier niveau.
    ---
    Les Donnees vont au joueur et non au monde : c'est tout le point de la
    reserve imperiale. Le reste va dans les soutes.
    """
    for material in ResourceType.materials():
        territory.add(type=material, amount=500000)
    territory.add(type=ResourceType.credits, amount=500000)
    territory.user.add_research(data)
    session.commit()


class TestResearchState:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_new_user_basis_technologies(self, client):
        """
        Un compte neuf porte l'arbre entier, tout a zero.
        """
        response = client.get('/api/technologies')

        assert response.status_code == 200
        assert len(response.json['technologies']) == len(TechnologyType)
        assert [t['level'] for t in response.json['technologies']] == \
            [0] * len(TechnologyType)

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_state_carries_what_the_cards_cannot(self, client):
        """
        La reserve, la production horaire et les emplacements : ce que le client
        affiche a cote des noeuds, et qu'une liste nue ne pouvait pas porter.
        """
        response = client.get('/api/technologies')

        assert response.status_code == 200
        assert response.json['research'] == 0
        assert response.json['used_slots'] == 0
        assert response.json['slots'] == 1
        assert set(response.json['branches']) == {b.name for b in Branch}

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_first_tier_node_is_available_and_a_deeper_one_is_locked(self, client):
        response = client.get('/api/technologies')
        cards = {t['type']: t for t in response.json['technologies']}

        assert cards['extraction']['state'] == 'available'
        assert cards['chantiers']['state'] == 'locked'
        assert cards['chantiers']['missing']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_tree_is_published_without_any_player_state(self, client):
        response = client.get('/api/technologies/tree')

        assert response.status_code == 200
        assert len(response.json['nodes']) == len(TechnologyType)
        assert len(response.json['branches']) == len(list(Branch))
        assert all('level' not in node for node in response.json['nodes'])


class TestTheCatalogueIsReadableByBothClients:
    """
    Le catalogue voyage vers deux clients qui ne lisent pas le JSON de la meme
    facon. La console interroge des objets indexes ; le client Unity passe par
    `JsonUtility`, qui ne sait construire que des champs connus a la
    compilation — un objet dont les cles sont les cent trente noms de l'arbre
    n'y arrive pas. Les deux formes coexistent donc, et ces tests-ci sont ce qui
    les empeche de diverger.
    """

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_prerequisites_say_the_same_thing_as_the_indexed_form(self, client):
        nodes = client.get('/api/technologies/tree').json['nodes']

        assert any(node['prerequisites'] for node in nodes)
        for node in nodes:
            assert {p['name']: p['level'] for p in node['prerequisites']} ==                 node['requires'], node['name']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_prerequisite_carries_the_label_it_will_be_shown_under(self, client):
        """
        Le client dessine le chemin d'acces sans avoir a retrouver chaque noeud
        cite dans le catalogue.
        """
        nodes = {n['name']: n for n in client.get('/api/technologies/tree').json['nodes']}
        prerequisite = nodes['chantiers']['prerequisites'][0]

        assert prerequisite['name'] == 'extraction'
        assert prerequisite['label'] == TechnologyType.extraction.label
        assert prerequisite['level'] == TechnologyType.chantiers.requires['extraction']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_unlocks_say_the_same_thing_in_both_forms(self, client):
        nodes = client.get('/api/technologies/tree').json['nodes']

        assert any(node['unlock_list'] for node in nodes)
        for node in nodes:
            flat = {(u['kind'], u['name']): u['level'] for u in node['unlock_list']}
            expected = {
                (kind, name): level
                for kind, found in node['unlocks'].items()
                for name, level in found.items()
            }
            assert flat == expected, node['name']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_tier_points_are_the_same_table_in_order(self, client):
        tree = client.get('/api/technologies/tree').json

        assert tree['tier_points'] == [
            tree['tiers'][str(tier)] for tier in sorted(int(t) for t in tree['tiers'])]
        assert tree['tier_points'][0] == 0
        assert tree['tier_points'] == sorted(tree['tier_points'])

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_node_can_be_placed_from_its_tier_alone(self, client):
        """
        La constellation pose un noeud a partir de son palier et de sa branche :
        les deux doivent etre sur chaque noeud du catalogue, sans lecture d'etat.
        """
        tree = client.get('/api/technologies/tree').json
        branches = {b['name'] for b in tree['branches']}

        for node in tree['nodes']:
            assert node['branch'] in branches, node['name']
            assert 1 <= node['tier'] <= len(tree['tier_points']), node['name']
            assert node['tier_requirement'] == tree['tier_points'][node['tier'] - 1]


class TestAnAccountThatMissedItsTree:
    """
    Un compte peut se retrouver sans aucune ligne de technologie : `User.new` ne
    pose l'arbre que si un territoire accompagne la creation, et
    `initialize.py` cree l'administrateur sans monde. Qu'il en recoive un plus
    tard le rendait jouable sans une seule technologie — l'arbre s'affichait
    entier, et aucun noeud ne s'ouvrait.
    """

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_reading_puts_back_what_is_missing(self, client, session):
        me = my_territory(client).user
        session.query(Technology).filter(Technology.user_id == me.id).delete()
        session.commit()
        assert Technology.levels(user=me) == {}

        response = client.get('/api/technologies')

        assert response.status_code == 200
        assert len(response.json['technologies']) == len(TechnologyType)
        assert [t['level'] for t in response.json['technologies']] ==             [0] * len(TechnologyType)

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_partial_tree_is_completed(self, client, session):
        """
        Le cas d'un arbre agrandi dont la migration n'a pas encore tourné : le
        joueur porte les anciens nœuds, pas les nouveaux.
        """
        me = my_territory(client).user
        kept = [t.name for t in list(TechnologyType)[:5]]
        session.query(Technology).filter(
            Technology.user_id == me.id,
            Technology.type.notin_([TechnologyType.get_by_name(n) for n in kept]),
        ).delete(synchronize_session=False)
        session.commit()
        assert len(Technology.levels(user=me)) == 5

        response = client.get('/api/technologies')

        assert len(response.json['technologies']) == len(TechnologyType)

    @pytest.mark.usefixtures("base_universe")
    def test_receiving_a_world_lays_the_tree(self, session, base_universe):
        """
        Recevoir un monde, c'est devenir jouable — et c'est là que l'arbre doit
        naître pour un compte créé sans territoire.
        """
        from app.models.game.system import System
        from app.models.user import User

        moderator = User.new(username="moderateur", password="x", email="m@t.com")
        session.commit()
        assert Technology.levels(user=moderator) == {}

        # Un systeme est tire au hasard : son nombre de mondes varie, et un
        # indice fixe tombait une fois sur cinq hors de la liste.
        free = None
        for n in range(2, 8):
            system = System.create(
                galaxy=base_universe["galaxy"], position="2_2_%d" % n)
            if system.territories:
                free = system.territories[0]
                break
        assert free is not None, "aucun systeme genere n'a de monde"

        free.assign(user=moderator)
        session.commit()

        assert len(Technology.levels(user=moderator)) == len(TechnologyType)


class TestResearchOrder:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_order_takes_a_slot_and_debits_the_empire(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)
        before = float(territory.user.research)

        response = client.post('/api/technology/extraction')

        assert response.status_code == 200
        assert response.json['eventType'] == 'research'

        response = client.get('/api/technologies')
        assert response.json['used_slots'] == 1
        assert response.json['research'] < before

        cards = {t['type']: t for t in response.json['technologies']}
        assert cards['extraction']['state'] == 'researching'

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_same_node_cannot_be_ordered_twice(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)

        assert client.post('/api/technology/extraction').status_code == 200
        response = client.post('/api/technology/extraction')

        assert response.status_code == 400
        assert 'déjà en recherche' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_second_order_needs_a_second_slot(self, client, session):
        """
        Un compte neuf n'a qu'un emplacement : c'est l'academie qui en ouvre
        d'autres, dix niveaux pour un.
        """
        territory = my_territory(client)
        bankroll(territory, session)

        assert client.post('/api/technology/extraction').status_code == 200
        response = client.post('/api/technology/metallurgie')

        assert response.status_code == 400
        assert 'emplacements' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_academies_open_the_slots(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)
        territory.add(type=BuildingType.academy, amount=20)
        session.commit()

        response = client.get('/api/technologies')
        assert response.json['slots'] == 3

        assert client.post('/api/technology/extraction').status_code == 200
        assert client.post('/api/technology/metallurgie').status_code == 200

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_locked_node_is_refused_with_its_reason(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)

        response = client.post('/api/technology/chantiers')

        assert response.status_code == 400
        assert 'Extraction assistée' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_unaffordable_node_is_refused(self, client):
        response = client.post('/api/technology/extraction')

        assert response.status_code == 400
        assert 'Ressources insuffisantes' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_unknown_node_is_refused(self, client):
        response = client.post('/api/technology/telepathie')

        assert response.status_code == 400
        assert 'inconnue' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_old_route_with_a_territory_still_answers(self, client, session):
        """
        Les clients deja livres postent encore `/api/technology/<nom>/<id>`.
        Le territoire est ignore — la depense se fait sur l'empire — mais la
        route ne doit pas leur repondre 404.
        """
        territory = my_territory(client)
        bankroll(territory, session)

        response = client.post(f'/api/technology/extraction/{territory.id}')

        assert response.status_code == 200


class TestResearchCompletion:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_finished_research_raises_the_level_and_frees_the_slot(
            self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)

        with freeze_time(datetime.datetime.utcnow()) as frozen:
            assert client.post('/api/technology/extraction').status_code == 200

            frozen.tick(datetime.timedelta(
                seconds=TechnologyType.extraction.base_time + 1))

            response = client.get('/api/technologies')
            cards = {t['type']: t for t in response.json['technologies']}

            assert cards['extraction']['level'] == 1
            assert cards['extraction']['state'] == 'owned'
            assert response.json['used_slots'] == 0

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_finished_research_produces_its_effect_without_being_looked_at(
            self, client, session):
        """
        Le niveau est encaisse a la premiere lecture des modificateurs, pas
        seulement quand le joueur ouvre l'ecran de recherche : `Extraction
        assistee` doit augmenter l'extraction meme s'il regarde ailleurs.
        """
        territory = my_territory(client)
        bankroll(territory, session)
        territory.add(type=BuildingType.mater_extractor, amount=5)
        session.commit()

        with freeze_time(datetime.datetime.utcnow()) as frozen:
            before = territory.get_hourly_gain(resource_type=ResourceType.iron)
            assert client.post('/api/technology/extraction').status_code == 200

            frozen.tick(datetime.timedelta(
                seconds=TechnologyType.extraction.base_time + 1))
            territory.user.forget_modifiers()

            after = territory.get_hourly_gain(resource_type=ResourceType.iron)
            assert after == pytest.approx(before * 1.03)


class TestResearchCancellation:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_cancelling_frees_the_slot_and_gives_half_back(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)

        before = float(territory.user.research)
        response = client.post('/api/technology/extraction')
        event_id = response.json['id']
        spent = before - float(territory.user.research)
        assert spent > 0

        response = client.delete(f'/api/technology/queue/{event_id}')
        assert response.status_code == 200

        response = client.get('/api/technologies')
        assert response.json['used_slots'] == 0
        assert response.json['research'] == pytest.approx(before - spent / 2)

        cards = {t['type']: t for t in response.json['technologies']}
        assert cards['extraction']['level'] == 0

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_cancelling_something_that_is_not_running_is_refused(self, client):
        response = client.delete('/api/technology/queue/4242')

        assert response.status_code == 400


class TestDoctrines:

    def open_the_doctrine(self, client, session):
        """
        Ouvre `Doctrine de flotte` sans jouer les trente-cinq niveaux qui y
        menent : les niveaux sont offerts, ce qui n'engage aucune ressource.
        """
        territory = my_territory(client)
        bankroll(territory, session, data=50000000)
        user = territory.user
        # `Doctrine de flotte` est au palier V : elle exige ses deux prerequis
        # nommes ET trente-six niveaux depenses dans Armement. On offre les deux,
        # ce qui n'engage aucune ressource — le sujet du test est la voie, pas le
        # chemin qui y mene.
        for name, level in (('alliages', 15), ('laser', 15), ('ogives', 12),
                            ('ciblage', 12), ('coques_renforcees', 12),
                            ('blindage_composite', 6)):
            technology = Technology.get(
                user=user, type=TechnologyType.get_by_name(name))
            while (technology.level or 0) < level:
                technology.increase(now=True)
        user.forget_modifiers()
        session.commit()
        return territory

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_doctrine_without_a_way_is_refused(self, client, session):
        self.open_the_doctrine(client, session)

        response = client.post('/api/technology/doctrine_de_flotte')

        assert response.status_code == 400
        assert 'Essaim' in response.json['message']

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_an_unknown_way_is_refused(self, client, session):
        self.open_the_doctrine(client, session)

        response = client.post(
            '/api/technology/doctrine_de_flotte', json={'choice': 'mutinerie'})

        assert response.status_code == 400

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_chosen_way_is_the_only_one_that_takes_effect(self, client, session):
        territory = self.open_the_doctrine(client, session)

        with freeze_time(datetime.datetime.utcnow()) as frozen:
            response = client.post(
                '/api/technology/doctrine_de_flotte', json={'choice': 'essaim'})
            assert response.status_code == 200

            frozen.tick(datetime.timedelta(
                seconds=TechnologyType.doctrine_de_flotte.base_time + 1))

            response = client.get('/api/technologies')
            cards = {t['type']: t for t in response.json['technologies']}

            assert cards['doctrine_de_flotte']['level'] == 1
            assert cards['doctrine_de_flotte']['choice'] == 'essaim'
            assert cards['doctrine_de_flotte']['state'] == 'maxed'

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_armed_way_is_visible_while_the_research_runs(self, client, session):
        """
        Une doctrine dure deux jours : le joueur doit voir laquelle des deux
        voies tourne, et pas une fiche muette jusqu'a la fin.
        """
        self.open_the_doctrine(client, session)

        assert client.post(
            '/api/technology/doctrine_de_flotte',
            json={'choice': 'ligne'}).status_code == 200

        response = client.get('/api/technologies')
        cards = {t['type']: t for t in response.json['technologies']}

        assert cards['doctrine_de_flotte']['state'] == 'researching'
        assert cards['doctrine_de_flotte']['choice'] == 'ligne'
        # Et les effets annonces sont ceux de la voie armee, pas de l'autre.
        labels = ' '.join(e['label'] for e in cards['doctrine_de_flotte']['effects'])
        assert 'coques lourdes' in labels

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_a_rank_refuses_a_way(self, client, session):
        territory = my_territory(client)
        bankroll(territory, session)

        response = client.post(
            '/api/technology/extraction', json={'choice': 'essaim'})

        assert response.status_code == 400
        assert "n'est pas une doctrine" in response.json['message']


class TestResearchIsPaidByTheWholeEmpire:

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_data_come_from_the_player_and_not_from_a_world(self, client, session):
        """
        La reserve de Donnees ne pend a aucun monde : c'est ce qui empeche le
        stock d'une seule planete de plafonner la recherche de tout l'empire.
        """
        territory = my_territory(client)
        bankroll(territory, session)
        before = dict(territory.resources)

        assert client.post('/api/technology/extraction').status_code == 200

        # Le fer et les credits sont bien pris sur le monde, les Donnees non :
        # elles ne figurent meme pas dans ce qu'un territoire detient.
        assert ResourceType.research not in before
        assert territory.user.research < 500000

    @pytest.mark.usefixtures("base_universe")
    @pytest.mark.usefixtures("authenticate_as_user")
    def test_the_academy_fills_the_reserve(self, client, session):
        """
        L'academie etait le seul batiment sans production : elle coutait cher et
        ne rendait rien. Elle rend les Donnees.
        """
        territory = my_territory(client)
        territory.add(type=BuildingType.academy, amount=3)
        session.commit()

        assert territory.get_hourly_gain(resource_type=ResourceType.research) > 0

        response = client.get('/api/technologies')
        assert response.json['research_gain'] > 0
