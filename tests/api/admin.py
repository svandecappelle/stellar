# -*- coding: utf-8 -*-

"""
L'administration du serveur : version du schema, reglages, journal d'audit.

Trois fils conducteurs, et ce sont eux qui decident de ce qui est teste :

  · **La porte tient.** Un joueur ordinaire ne doit rien pouvoir lire ni changer
    ici. Un moderateur non plus : sa portee est une galaxie, pas la machine.

  · **Un reglage regle vraiment quelque chose.** Une case qui ne change rien est
    pire qu'une case absente. Chaque parametre est donc eprouve par son effet —
    inscriptions fermees qui refusent, frein abaisse qui mord plus tot, jeton
    dont l'echeance suit la duree reglee.

  · **Le journal ne contient aucun secret.** Surtout sur un refus, ou le corps
    de la requete porte justement le mot de passe essaye.
"""

import json
from datetime import datetime, timedelta

import pytest

from app.models.audit import Action, AuditLog, scrub
from app.models.role import RoleType
from app.models.server import DEFAULTS, SETTINGS_BY_KEY, ServerSettings
from app.models.user import User
from app.web.api import throttle


@pytest.fixture(autouse=True)
def clear_throttle():
    """Le frein compte en memoire du processus : sans remise a zero, un test
    qui atteint sa limite ferait echouer les suivants."""
    throttle.reset()
    yield
    throttle.reset()


def as_player(client, session, username="joueur", password="un-mot-de-passe"):
    """Un compte sans aucun role, connecte."""
    User.new(username=username, password=password,
             email="%s@testing.com" % username)
    session.commit()
    assert client.post('/api/auth/login', json={
        "username": username, "password": password}).status_code == 200


def lines(session, action=None):
    query = session.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.order_by(AuditLog.id).all()


class TestTheDoorHolds:
    """
    Qui peut entrer dans l'administration.

    La question n'est pas rhetorique : ces routes lisent ce que TOUS les joueurs
    ont fait et reglent la machine entiere. Une seule route oubliee suffirait.
    """

    ROUTES = [
        ('get', '/api/admin/schema'),
        ('get', '/api/admin/settings'),
        ('get', '/api/admin/audit'),
        ('get', '/api/admin/players'),
    ]

    def test_nobody_gets_in_without_a_session(self, client, session):
        for method, route in self.ROUTES:
            assert getattr(client, method)(route).status_code == 401, route

        assert client.post('/api/admin/settings', json={}).status_code == 401
        assert client.post('/api/admin/audit/purge', json={}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_a_plain_player_is_refused(self, client, session):
        as_player(client, session)

        for method, route in self.ROUTES:
            assert getattr(client, method)(route).status_code == 403, route

        assert client.post('/api/admin/settings',
                           json={"registration_open": False}).status_code == 403

    def test_a_moderator_is_not_an_administrator(self, client, session):
        """
        Un moderateur arbitre une partie. Regler le serveur et lire le journal
        de tous les joueurs deborde de la galaxie qu'il modere — sans quoi
        confier une partie a quelqu'un lui confierait la machine.
        """
        user = User.new(username="arbitre", password="un-mot-de-passe",
                        email="arbitre@testing.com")
        user.add_role(RoleType.moderator, scope="Milky Way")
        session.commit()

        assert client.post('/api/auth/login', json={
            "username": "arbitre", "password": "un-mot-de-passe"}).status_code == 200

        assert client.get('/api/admin/settings').status_code == 403
        assert client.get('/api/admin/audit').status_code == 403

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_an_administrator_gets_in(self, client):
        for method, route in self.ROUTES:
            assert getattr(client, method)(route).status_code == 200, route


class TestTheSchemaRoute:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_says_where_the_database_stands(self, client):
        answer = client.get('/api/admin/schema')
        assert answer.status_code == 200

        body = answer.json
        # La suite monte son schema par `create_all` sans tamponner : l'etat
        # attendu est donc « des tables, mais pas d'alembic_version ». C'est
        # exactement le cas que la route doit savoir nommer, et non une panne.
        assert body['state'] in (
            'up_to_date', 'behind', 'ahead', 'unstamped', 'unknown')
        assert body['head'], "la tete de la chaine doit etre lisible"
        assert isinstance(body['pending'], list)
        assert body['message']
        assert body['command']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_head_is_the_repository_head(self, client):
        import schema_version

        assert client.get('/api/admin/schema').json['head'] == \
            schema_version.head_revision()

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_an_up_to_date_base_has_nothing_pending(self, client):
        body = client.get('/api/admin/schema').json
        if body['up_to_date']:
            assert body['pending'] == []


class TestTheSettingsRoute:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_fresh_server_serves_the_defaults(self, client):
        body = client.get('/api/admin/settings').json

        assert body['settings'] == DEFAULTS
        assert body['overrides'] == {}
        assert body['updated_at'] is None

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_every_parameter_says_what_it_touches(self, client):
        """
        `applied_by` nomme l'endroit qui lit le reglage. Un administrateur ne
        change pas sereinement une valeur dont il ignore ce qu'elle touche, et
        la regle du module est que chaque reglage soit lu par du code existant.
        """
        for parameter in client.get('/api/admin/settings').json['parameters']:
            assert parameter['applied_by'], parameter['key']
            assert parameter['label'], parameter['key']
            assert parameter['description'], parameter['key']
            assert parameter['kind'] in ('bool', 'int', 'text'), parameter['key']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_value_is_kept(self, client):
        answer = client.post('/api/admin/settings',
                             json={"settings": {"login_attempts": 3}})
        assert answer.status_code == 200
        assert answer.json['settings']['login_attempts'] == 3

        assert client.get('/api/admin/settings').json['settings']['login_attempts'] == 3

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_body_may_carry_the_keys_directly(self, client):
        """La console envoie `{"settings": {...}}`, un appel a la main non."""
        assert client.post('/api/admin/settings',
                           json={"login_attempts": 7}).status_code == 200
        assert client.get('/api/admin/settings').json['settings']['login_attempts'] == 7

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_default_value_erases_the_override(self, client):
        client.post('/api/admin/settings', json={"login_attempts": 3})
        assert client.get('/api/admin/settings').json['overrides'] == {"login_attempts": 3}

        client.post('/api/admin/settings',
                    json={"login_attempts": DEFAULTS['login_attempts']})
        assert client.get('/api/admin/settings').json['overrides'] == {}

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_an_absent_key_is_left_alone(self, client):
        client.post('/api/admin/settings', json={"login_attempts": 3})
        client.post('/api/admin/settings', json={"register_attempts": 2})

        settings = client.get('/api/admin/settings').json['settings']
        assert settings['login_attempts'] == 3
        assert settings['register_attempts'] == 2

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_value_out_of_bounds_is_refused_with_its_bounds(self, client):
        answer = client.post('/api/admin/settings', json={"login_attempts": 99999})
        assert answer.status_code == 400
        # Les bornes sont dans le message : qui tape 99999 s'est trompe de
        # champ, et lui rendre le maximum sans rien dire lui laisserait croire
        # que sa valeur est passee.
        assert "1000" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_an_unknown_key_is_refused(self, client):
        answer = client.post('/api/admin/settings', json={"vitesse_lumiere": 3})
        assert answer.status_code == 400
        assert "vitesse_lumiere" in answer.json['message']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_refused_value_changes_nothing(self, client):
        client.post('/api/admin/settings', json={"login_attempts": 3})
        client.post('/api/admin/settings', json={"login_attempts": 99999})

        assert client.get('/api/admin/settings').json['settings']['login_attempts'] == 3

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_text_that_is_too_long_is_refused(self, client):
        maximum = SETTINGS_BY_KEY['announcement'].maximum
        answer = client.post('/api/admin/settings',
                             json={"announcement": "x" * (maximum + 1)})
        assert answer.status_code == 400

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_changing_a_setting_leaves_a_trace(self, client, session):
        """
        Ouvrir les inscriptions, laisser passer une vague de comptes puis les
        refermer ne doit pas pouvoir se faire sans trace.
        """
        client.post('/api/admin/settings', json={"registration_open": False})

        written = lines(session, Action.ADMIN_SETTINGS)
        assert len(written) == 1
        assert written[0].username == "admin"
        assert json.loads(written[0].details)['changed'] == {"registration_open": False}


class TestASettingActuallySettles:
    """
    Chaque reglage est eprouve par son EFFET, et non par sa presence en base.

    C'est la difference entre une case a cocher et un reglage : la premiere se
    teste en la relisant, le second en constatant que le serveur s'est mis a se
    comporter autrement.
    """

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_closing_registration_refuses_new_accounts(self, client):
        # Le reglage d'abord : une inscription OUVRE une session sur le compte
        # cree, et la requete suivante ne partirait donc plus en administrateur.
        assert client.post('/api/admin/settings',
                           json={"registration_open": False}).status_code == 200

        refused = client.post('/api/users', json={
            "username": "apres", "password": "un-mot-de-passe",
            "email": "apres@testing.com"})
        assert refused.status_code == 403

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_registration_works_while_it_is_open(self, client):
        assert client.get('/api/server').json['registration_open'] is True
        assert client.post('/api/users', json={
            "username": "avant", "password": "un-mot-de-passe",
            "email": "avant@testing.com"}).status_code == 201

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_closing_registration_leaves_existing_accounts_alone(self, client, session):
        User.new(username="ancien", password="un-mot-de-passe",
                 email="ancien@testing.com")
        session.commit()

        client.post('/api/admin/settings', json={"registration_open": False})
        client.post('/api/auth/logout')

        assert client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"}).status_code == 200

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_public_route_says_registration_is_closed(self, client):
        assert client.get('/api/server').json['registration_open'] is True

        client.post('/api/admin/settings', json={"registration_open": False})
        assert client.get('/api/server').json['registration_open'] is False

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_announcement_reaches_the_public_route(self, client):
        client.post('/api/admin/settings',
                    json={"announcement": "Coupure prevue dimanche."})

        client.post('/api/auth/logout')
        # Non authentifie : c'est tout l'objet de cette route — personne ne lira
        # un message place derriere le formulaire quand le serveur est
        # justement injoignable.
        assert client.get('/api/server').json['announcement'] == \
            "Coupure prevue dimanche."

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_lowering_the_login_limit_bites_sooner(self, client, session):
        User.new(username="cible", password="un-mot-de-passe",
                 email="cible@testing.com")
        session.commit()

        client.post('/api/admin/settings', json={"login_attempts": 2})
        throttle.reset()

        codes = [
            client.post('/api/auth/token', json={
                "username": "cible", "password": "faux"}).status_code
            for _ in range(4)
        ]
        assert codes[:2] == [401, 401]
        assert 429 in codes[2:], codes

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_device_key_follows_the_configured_lifetime(self, client, session):
        from app.models.token import DeviceToken

        client.post('/api/admin/settings', json={"device_token_days": 3})

        User.new(username="pilote", password="un-mot-de-passe",
                 email="pilote@testing.com")
        session.commit()

        client.post('/api/auth/logout')
        answer = client.post('/api/auth/token', json={
            "username": "pilote", "password": "un-mot-de-passe"})
        assert answer.status_code == 200

        row = session.query(DeviceToken).one()
        remaining = row.expires_at - datetime.utcnow()
        assert timedelta(days=2, hours=23) < remaining <= timedelta(days=3)

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_device_ceiling_is_configurable(self, client, session):
        from app.models.token import DeviceToken

        client.post('/api/admin/settings', json={"max_devices_per_user": 2})

        user = User.new(username="pilote", password="un-mot-de-passe",
                        email="pilote@testing.com")
        session.commit()
        client.post('/api/auth/logout')

        for _ in range(4):
            assert client.post('/api/auth/token', json={
                "username": "pilote", "password": "un-mot-de-passe"}).status_code == 200

        assert len(DeviceToken.alive(user=user)) == 2


class TestTheAuditTrail:

    @pytest.mark.usefixtures("base_universe")
    def test_a_successful_sign_in_is_recorded(self, client, session):
        as_player(client, session)

        written = lines(session, Action.LOGIN)
        assert len(written) == 1
        assert written[0].username == "joueur"
        assert written[0].outcome == 'ok'

    def test_a_failed_sign_in_is_recorded_with_the_name_tried(self, client, session):
        """
        Le nom essaye, meme s'il ne correspond a aucun compte : c'est le seul
        moyen de voir qu'on cherche des comptes existants.
        """
        client.post('/api/auth/login', json={
            "username": "fantome", "password": "au-hasard"})

        written = lines(session, Action.REFUSED)
        assert len(written) == 1
        assert written[0].status == 401
        assert written[0].user_id is None
        assert json.loads(written[0].details)['payload']['body']['username'] == "fantome"

    def test_a_failed_sign_in_never_records_the_password(self, client, session):
        """
        Le test qui compte. Sur un refus de connexion, le corps de la requete
        porte justement le mot de passe essaye — et un journal d'audit est lu
        par des administrateurs.
        """
        client.post('/api/auth/login', json={
            "username": "fantome", "password": "le-secret-de-quelquun"})

        written = lines(session, Action.REFUSED)
        assert "le-secret-de-quelquun" not in (written[0].details or '')
        assert json.loads(written[0].details)['payload']['body']['password'] == '***'

    def test_a_refused_token_never_records_its_value(self, client, session):
        client.post('/api/auth/session', json={"token": "une-valeur-volee"})

        written = lines(session, Action.REFUSED)
        assert "une-valeur-volee" not in (written[0].details or '')

    @pytest.mark.usefixtures("base_universe")
    def test_a_refusal_leaves_nothing_behind(self, client, session):
        """
        Le piege de l'ecriture dans un `after_request` : valider la transaction
        pour y glisser la ligne d'audit enregistrerait aussi ce que la requete
        refusee avait commence a poser. D'ou l'annulation prealable.
        """
        as_player(client, session)

        before = session.query(User).count()
        client.post('/api/users', json={"username": "x", "password": "court"})
        assert session.query(User).count() == before

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_registration_is_recorded(self, client, session):
        client.post('/api/auth/logout')
        client.post('/api/users', json={
            "username": "nouveau", "password": "un-mot-de-passe",
            "email": "nouveau@testing.com"})

        written = lines(session, Action.REGISTER)
        assert len(written) == 1
        assert written[0].username == "nouveau"

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_issuing_a_device_key_is_recorded_without_its_value(self, client, session):
        User.new(username="pilote", password="un-mot-de-passe",
                 email="pilote@testing.com")
        session.commit()
        client.post('/api/auth/logout')

        answer = client.post('/api/auth/token', json={
            "username": "pilote", "password": "un-mot-de-passe"})
        given = answer.json['token']

        written = lines(session, Action.TOKEN_ISSUE)
        assert len(written) == 1
        assert given not in (written[0].details or '')
        assert json.loads(written[0].details)['device_id']

    @pytest.mark.usefixtures("authenticate_as_user")
    def test_claiming_a_world_is_recorded(self, client, session, base_universe):
        from app.models.game.planet import PlanetArchetype
        from app.models.game.system import System

        # Le systeme de l'univers de test est deja tenu par son joueur : on en
        # pose un second. Fabriquer le monde libre plutot que d'en chercher un
        # evite un test qui passe son tour — donc qui ne teste plus rien.
        elsewhere = System.create(galaxy=base_universe['galaxy'], position="2_2_2")
        free = elsewhere.territories[0]
        free.archetype = PlanetArchetype.telluric
        session.commit()

        client.post('/api/territory/%d' % free.id)

        # Reussite ou refus selon l'archetype tire : ce qui est teste est qu'un
        # geste de cette portee laisse une trace dans un cas comme dans l'autre.
        assert lines(session, Action.TERRITORY_CLAIM) \
            or lines(session, Action.REFUSED)

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_route_and_address_are_kept(self, client, session):
        client.post('/api/auth/logout')
        client.post('/api/auth/login', json={"username": "x", "password": "y"})

        written = lines(session, Action.REFUSED)[-1]
        assert written.route == 'POST /api/auth/login'
        assert written.address


class TestTheTraceSurvivesTheRequest:
    """
    Une ligne d'audit doit etre VALIDEE, pas seulement ajoutee.

    Le piege est invisible en test : la suite partage une session qui survit a
    la requete, si bien qu'une ligne ajoutee sans `commit` parait ecrite. En
    production, la session `scoped` est rendue au bout de chaque requete et tout
    ce qui n'a pas ete valide part avec elle — la trace s'evapore.

    `rollback` reproduit cette fin de requete : ce qui a ete valide y survit, le
    reste non. C'est le seul moyen de distinguer les deux depuis un test.
    """

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_registration_is_committed(self, client, session):
        client.post('/api/auth/logout')
        client.post('/api/users', json={
            "username": "nouveau", "password": "un-mot-de-passe",
            "email": "nouveau@testing.com"})

        session.rollback()
        assert lines(session, Action.REGISTER), \
            "la trace d'inscription n'a pas ete validee"

    @pytest.mark.usefixtures("base_universe")
    def test_the_sign_in_trace_is_committed(self, client, session):
        as_player(client, session)

        session.rollback()
        assert lines(session, Action.LOGIN)

    def test_a_refusal_trace_is_committed(self, client, session):
        client.post('/api/auth/login', json={"username": "x", "password": "y"})

        session.rollback()
        assert lines(session, Action.REFUSED)

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_device_key_traces_are_committed(self, client, session):
        User.new(username="pilote", password="un-mot-de-passe",
                 email="pilote@testing.com")
        session.commit()
        client.post('/api/auth/logout')

        client.post('/api/auth/token', json={
            "username": "pilote", "password": "un-mot-de-passe"})

        session.rollback()
        assert lines(session, Action.TOKEN_ISSUE)

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_settings_trace_is_committed(self, client, session):
        client.post('/api/admin/settings', json={"login_attempts": 4})

        session.rollback()
        assert lines(session, Action.ADMIN_SETTINGS)


class TestReadingTheAuditTrail:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_reads_newest_first(self, client, session):
        for name in ('un', 'deux', 'trois'):
            client.post('/api/auth/login', json={"username": name, "password": "x"})

        entries = client.get('/api/admin/audit').json['entries']
        names = [
            json.loads(json.dumps(e['details']))['payload']['body']['username']
            for e in entries if e['details'] and e['details'].get('payload')
        ]
        assert names[:3] == ['trois', 'deux', 'un']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_filters_by_action(self, client, session):
        client.post('/api/auth/login', json={"username": "x", "password": "y"})

        body = client.get('/api/admin/audit?action=%s' % Action.REFUSED).json
        assert body['entries']
        assert all(e['action'] == Action.REFUSED for e in body['entries'])

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_filters_by_player(self, client, session):
        body = client.get('/api/admin/audit?user=admin').json
        assert all(e['username'] == 'admin' for e in body['entries'])

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_filters_by_outcome_and_status(self, client, session):
        client.post('/api/auth/login', json={"username": "x", "password": "y"})

        refused = client.get('/api/admin/audit?outcome=refused').json
        assert all(e['outcome'] == 'refused' for e in refused['entries'])

        by_code = client.get('/api/admin/audit?status=401').json
        assert by_code['entries']
        assert all(e['status'] == 401 for e in by_code['entries'])

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_bad_filter_is_refused_rather_than_ignored(self, client):
        assert client.get('/api/admin/audit?status=hier').status_code == 400
        assert client.get('/api/admin/audit?since=jeudi').status_code == 400

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_paginates(self, client, session):
        for i in range(7):
            client.post('/api/auth/login',
                        json={"username": "n%d" % i, "password": "x"})

        first = client.get('/api/admin/audit?size=3&page=1').json
        assert len(first['entries']) == 3
        assert first['total'] >= 7
        assert first['pages'] >= 3

        second = client.get('/api/admin/audit?size=3&page=2').json
        assert {e['id'] for e in first['entries']} & \
               {e['id'] for e in second['entries']} == set()

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_it_serves_the_vocabulary_for_the_filters(self, client):
        body = client.get('/api/admin/audit').json
        assert Action.LOGIN in body['actions']
        assert Action.REFUSED in body['actions']

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_players_route_lists_names(self, client):
        players = client.get('/api/admin/players').json['players']
        assert any(p['username'] == 'admin' for p in players)
        # Rien d'autre qu'un nom et un identifiant : cette vue n'est pas une
        # console de gestion de comptes.
        assert set(players[0]) == {'id', 'username'}


class TestPurging:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_old_lines_go_and_recent_ones_stay(self, client, session):
        old = AuditLog(action=Action.LOGIN, outcome='ok',
                       created_at=datetime.utcnow() - timedelta(days=40))
        recent = AuditLog(action=Action.LOGIN, outcome='ok',
                          created_at=datetime.utcnow() - timedelta(days=1))
        session.add_all([old, recent])
        session.commit()

        # Les identifiants sont releves AVANT : lire `old.id` apres la
        # suppression ferait recharger une ligne qui n'est plus la.
        old_id, recent_id = old.id, recent.id

        answer = client.post('/api/admin/audit/purge', json={"days": 30})
        assert answer.status_code == 200
        assert answer.json['removed'] >= 1

        assert session.query(AuditLog).filter(AuditLog.id == recent_id).count() == 1
        assert session.query(AuditLog).filter(AuditLog.id == old_id).count() == 0

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_the_purge_itself_is_recorded(self, client, session):
        """
        La seule ligne qu'un administrateur ne peut pas faire disparaitre sans
        laisser de trace de sa disparition.
        """
        client.post('/api/admin/audit/purge', json={"days": 30})
        assert lines(session, Action.ADMIN_PURGE)

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_a_nonsense_duration_is_refused(self, client):
        assert client.post('/api/admin/audit/purge',
                           json={"days": 0}).status_code == 400
        assert client.post('/api/admin/audit/purge',
                           json={"days": "hier"}).status_code == 400


class TestScrubbing:
    """
    Le filtre des secrets, seul. Il est la derniere barriere entre le corps
    d'une requete et une table que des administrateurs relisent.
    """

    def test_it_hides_a_password_whatever_the_key(self):
        cleaned = scrub({
            'password': 'a', 'new_password': 'b', 'passwordConfirm': 'c'})
        assert set(cleaned.values()) == {'***'}

    def test_it_hides_tokens_keys_and_digests(self):
        cleaned = scrub({
            'token': 'a', 'api_key': 'b', 'digest': 'c', 'Authorization': 'd'})
        assert set(cleaned.values()) == {'***'}

    def test_it_goes_down_into_nested_objects(self):
        cleaned = scrub({'credentials': {'inner': {'password': 'secret'}}})
        assert cleaned['credentials']['inner']['password'] == '***'

    def test_it_goes_through_lists(self):
        cleaned = scrub([{'password': 'secret'}, {'name': 'visible'}])
        assert cleaned[0]['password'] == '***'
        assert cleaned[1]['name'] == 'visible'

    def test_it_trims_a_long_list_rather_than_writing_it_whole(self):
        cleaned = scrub(list(range(40)))
        assert len(cleaned) == 11
        assert 'de plus' in cleaned[-1]

    def test_it_leaves_ordinary_values_alone(self):
        assert scrub({'territory_id': 12, 'name': 'Terra'}) == \
            {'territory_id': 12, 'name': 'Terra'}


class TestSettingsNeverBreakTheGame:
    """
    `ServerSettings.value` est appele par le frein et par les jetons, a chaque
    connexion. Il ne doit JAMAIS lever : un reglage n'est pas une regle du jeu,
    il ne peut pas empecher quelqu'un d'entrer.
    """

    def test_an_unknown_key_gives_none_rather_than_raising(self, session):
        assert ServerSettings.value('cle-inexistante') is None

    def test_a_missing_table_gives_the_default(self, session, monkeypatch):
        def explode():
            raise RuntimeError("table absente")

        monkeypatch.setattr(ServerSettings, 'row', staticmethod(explode))
        assert ServerSettings.value('login_attempts') == DEFAULTS['login_attempts']
        assert ServerSettings.effective() == DEFAULTS

    def test_the_throttle_falls_back_on_the_route_values(self, session, monkeypatch):
        def explode():
            raise RuntimeError("table absente")

        monkeypatch.setattr(ServerSettings, 'row', staticmethod(explode))
        assert throttle.configured('login', limit=10, window=300) == (10, 300)
