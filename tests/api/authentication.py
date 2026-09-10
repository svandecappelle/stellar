# -*- coding: utf-8 -*-

"""
L'inscription, la connexion et les jetons d'appareil, de bout en bout.

Ce que les tests unitaires de `app/security.py` ne peuvent pas couvrir : tout ce
qui passe par la base et par une session. Un compte cree, un jeton remis puis
represente, un appareil deconnecte, un mot de passe converti au passage.

Le fil conducteur de ce fichier : **un refus ne doit rien apprendre.** Un
serveur qui distingue « ce compte n'existe pas » de « ce n'est pas le bon mot de
passe » remet sa liste de comptes a qui prend la peine de la demander, et c'est
le genre de fuite qu'aucun journal ne signale.
"""

import hashlib
from datetime import datetime, timedelta

import pytest

from app.models.token import DeviceToken, LIFETIME_DAYS, MAX_PER_USER
from app.models.user import User
from app.security import LEGACY_HASH, token_digest
from app.web.api import throttle


@pytest.fixture(autouse=True)
def clear_throttle():
    """
    Le frein compte en memoire du processus : sans remise a zero, le premier
    test qui atteint sa limite ferait echouer tous les suivants.
    """
    throttle.reset()
    yield
    throttle.reset()


def signup(client, username="pilote", password="un-mot-de-passe",
           email="pilote@testing.com"):
    return client.post('/api/users', json={
        "username": username, "password": password, "email": email})


def get_token(client, username="pilote", password="un-mot-de-passe",
              device="Windows · poste de test"):
    return client.post('/api/auth/token', json={
        "username": username, "password": password, "device": device})


class TestSigningUp:

    @pytest.mark.usefixtures("base_universe")
    def test_a_new_account_is_created_and_signed_in(self, client, session):
        response = signup(client)

        assert response.status_code == 201
        assert response.json['username'] == "pilote"
        assert User.exists(username="pilote")

        # La session est ouverte dans la foulee : redemander au joueur de se
        # connecter juste apres s'etre inscrit n'apporte rien.
        assert client.get('/api/auth').status_code == 200

    @pytest.mark.usefixtures("base_universe")
    def test_the_password_is_never_stored_as_given(self, client, session):
        signup(client, password="un-mot-de-passe")

        stored = User.get(username="pilote").password

        assert "un-mot-de-passe" not in stored
        assert not LEGACY_HASH.match(stored)

    @pytest.mark.usefixtures("base_universe")
    def test_the_answer_never_carries_the_password(self, client, session):
        response = signup(client, password="un-mot-de-passe")

        assert 'password' not in response.json
        assert "un-mot-de-passe" not in response.get_data(as_text=True)

    @pytest.mark.usefixtures("base_universe")
    def test_a_new_account_owns_no_world(self, client, session):
        """
        Le compte nait sans monde : c'est le parcours de reclamation qui prend
        la suite, et c'est cette attribution-la qui pose l'arbre technologique.
        """
        signup(client)

        assert User.get(username="pilote").territories == []

    @pytest.mark.usefixtures("base_universe")
    def test_a_short_password_is_refused(self, client, session):
        response = signup(client, password="court")

        assert response.status_code == 400
        assert not User.exists(username="pilote")

    @pytest.mark.usefixtures("base_universe")
    def test_a_name_already_taken_is_refused(self, client, session):
        signup(client)
        response = signup(client, email="autre@testing.com")

        assert response.status_code == 409

    @pytest.mark.parametrize("username", ["", "ab", "x" * 33])
    @pytest.mark.usefixtures("base_universe")
    def test_an_unusable_name_is_refused(self, client, session, username):
        assert signup(client, username=username).status_code == 400

    @pytest.mark.parametrize("email", ["", "pas-une-adresse", "a@b"])
    @pytest.mark.usefixtures("base_universe")
    def test_an_unusable_email_is_refused(self, client, session, email):
        assert signup(client, email=email).status_code == 400

    @pytest.mark.usefixtures("base_universe")
    def test_an_empty_body_is_refused_and_does_not_raise(self, client, session):
        assert client.post('/api/users', json={}).status_code == 400
        assert client.post('/api/users').status_code == 400


class TestTheDoorDoesNotTalk:
    """
    Un refus de connexion doit etre le meme, quoi qu'il se soit passe.
    """

    @pytest.mark.usefixtures("base_universe")
    def test_an_unknown_account_and_a_wrong_password_answer_alike(
            self, client, session):
        signup(client)

        unknown = client.post('/api/auth/login', json={
            "username": "personne", "password": "un-mot-de-passe"})
        wrong = client.post('/api/auth/login', json={
            "username": "pilote", "password": "pas-le-bon"})

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.get_data(as_text=True) == wrong.get_data(as_text=True)

    @pytest.mark.usefixtures("base_universe")
    def test_the_token_route_answers_the_same_way(self, client, session):
        signup(client)

        unknown = get_token(client, username="personne")
        wrong = get_token(client, password="pas-le-bon")

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.get_data(as_text=True) == wrong.get_data(as_text=True)


class TestTheAccountsThatCameBefore:
    """
    Les comptes ranges en SHA-256 nu, avant scrypt.
    """

    @staticmethod
    def make_legacy(session, username="ancien", password="un-mot-de-passe"):
        user = User.new(username=username, password=password,
                        email="a@testing.com")
        # On remet la main sur l'ancienne forme : c'est exactement ce que
        # `User.new` posait avant.
        user.password = hashlib.sha256(password.encode('utf-8')).hexdigest()
        session.commit()
        return user

    @pytest.mark.usefixtures("base_universe")
    def test_a_legacy_account_can_still_sign_in(self, client, session):
        self.make_legacy(session)

        response = client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"})

        assert response.status_code == 200

    @pytest.mark.usefixtures("base_universe")
    def test_signing_in_converts_the_password(self, client, session):
        """
        Une empreinte ne se remonte pas : la conversion ne peut avoir lieu qu'au
        seul instant ou le serveur tient le mot de passe en clair.
        """
        self.make_legacy(session)
        assert LEGACY_HASH.match(User.get(username="ancien").password)

        client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"})

        assert not LEGACY_HASH.match(User.get(username="ancien").password)

    @pytest.mark.usefixtures("base_universe")
    def test_the_conversion_survives_the_request(self, client, session):
        """
        Sans `commit`, la conversion serait refaite a chaque connexion — et le
        travail de scrypt paye pour rien, indefiniment.
        """
        self.make_legacy(session)
        client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"})
        converted = User.get(username="ancien").password

        client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"})

        assert User.get(username="ancien").password == converted

    @pytest.mark.usefixtures("base_universe")
    def test_the_password_still_works_after_the_conversion(self, client, session):
        self.make_legacy(session)
        client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"})

        assert client.post('/api/auth/login', json={
            "username": "ancien", "password": "un-mot-de-passe"}).status_code == 200
        assert client.post('/api/auth/login', json={
            "username": "ancien", "password": "pas-le-bon"}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_the_token_route_converts_it_too(self, client, session):
        self.make_legacy(session)

        assert get_token(client, username="ancien").status_code == 200
        assert not LEGACY_HASH.match(User.get(username="ancien").password)


class TestDeviceTokens:

    @pytest.mark.usefixtures("base_universe")
    def test_credentials_buy_a_token(self, client, session):
        signup(client)

        response = get_token(client)

        assert response.status_code == 200
        assert len(response.json['token']) >= 40
        assert response.json['device']['label'] == "Windows · poste de test"
        assert response.json['user']['username'] == "pilote"

    @pytest.mark.usefixtures("base_universe")
    def test_the_server_keeps_only_the_digest(self, client, session):
        signup(client)
        plain = get_token(client).json['token']

        row = session.query(DeviceToken).one()

        assert row.digest == token_digest(plain)
        assert plain not in row.digest

    @pytest.mark.usefixtures("base_universe")
    def test_a_token_reopens_a_session(self, client, session):
        signup(client)
        plain = get_token(client).json['token']
        client.post('/api/auth/logout')
        assert client.get('/api/auth').status_code == 401

        response = client.post('/api/auth/session', json={"token": plain})

        assert response.status_code == 200
        assert response.json['user']['username'] == "pilote"
        assert client.get('/api/auth').status_code == 200

    @pytest.mark.usefixtures("base_universe")
    def test_using_a_token_pushes_its_deadline_back(self, client, session):
        signup(client)
        plain = get_token(client).json['token']

        row = session.query(DeviceToken).one()
        row.expires_at = datetime.utcnow() + timedelta(days=1)
        row.last_used_at = None
        session.commit()

        client.post('/api/auth/session', json={"token": plain})

        refreshed = session.query(DeviceToken).one()
        assert refreshed.last_used_at is not None
        assert refreshed.expires_at > datetime.utcnow() + timedelta(days=LIFETIME_DAYS - 1)

    @pytest.mark.parametrize("given", ["", "n'importe quoi", None])
    @pytest.mark.usefixtures("base_universe")
    def test_a_token_that_is_not_one_is_refused(self, client, session, given):
        assert client.post(
            '/api/auth/session', json={"token": given}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_an_expired_token_no_longer_opens_anything(self, client, session):
        signup(client)
        plain = get_token(client).json['token']

        row = session.query(DeviceToken).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

        assert client.post(
            '/api/auth/session', json={"token": plain}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_an_expired_token_is_refused_like_an_unknown_one(self, client, session):
        """
        Distinguer les deux dirait a qui essaie des valeurs lesquelles ont
        existe.
        """
        signup(client)
        plain = get_token(client).json['token']
        row = session.query(DeviceToken).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()

        expired = client.post('/api/auth/session', json={"token": plain})
        unknown = client.post('/api/auth/session', json={"token": "inconnu"})

        assert expired.get_data(as_text=True) == unknown.get_data(as_text=True)


class TestDisconnectingADevice:

    @pytest.mark.usefixtures("base_universe")
    def test_the_devices_are_listed(self, client, session):
        signup(client)
        get_token(client, device="poste un")
        get_token(client, device="poste deux")

        response = client.get('/api/auth/tokens')

        assert response.status_code == 200
        assert {d['label'] for d in response.json['devices']} == {
            "poste un", "poste deux"}

    @pytest.mark.usefixtures("base_universe")
    def test_the_listing_never_carries_a_token(self, client, session):
        signup(client)
        plain = get_token(client).json['token']

        body = client.get('/api/auth/tokens').get_data(as_text=True)

        assert plain not in body
        assert token_digest(plain) not in body

    @pytest.mark.usefixtures("base_universe")
    def test_a_revoked_device_no_longer_opens_anything(self, client, session):
        signup(client)
        plain = get_token(client).json['token']
        device = client.get('/api/auth/tokens').json['devices'][0]

        assert client.delete(
            '/api/auth/token/%d' % device['id']).status_code == 200

        client.post('/api/auth/logout')
        assert client.post(
            '/api/auth/session', json={"token": plain}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_a_revoked_device_leaves_the_list(self, client, session):
        signup(client)
        get_token(client)
        device = client.get('/api/auth/tokens').json['devices'][0]

        client.delete('/api/auth/token/%d' % device['id'])

        assert client.get('/api/auth/tokens').json['devices'] == []

    @pytest.mark.usefixtures("base_universe")
    def test_a_device_of_someone_else_is_not_found(self, client, session):
        """
        404 et non 403 : repondre « interdit » confirmerait qu'il existe.
        """
        signup(client, username="pilote")
        get_token(client)
        mine = client.get('/api/auth/tokens').json['devices'][0]['id']
        client.post('/api/auth/logout')

        signup(client, username="autre", email="autre@testing.com")

        assert client.delete('/api/auth/token/%d' % mine).status_code == 404

    @pytest.mark.usefixtures("base_universe")
    def test_every_device_can_be_disconnected_at_once(self, client, session):
        signup(client)
        first = get_token(client, device="un").json['token']
        second = get_token(client, device="deux").json['token']

        response = client.delete('/api/auth/tokens')

        assert response.status_code == 200
        assert response.json['revoked'] == 2

        client.post('/api/auth/logout')
        for plain in (first, second):
            assert client.post(
                '/api/auth/session', json={"token": plain}).status_code == 401

    @pytest.mark.usefixtures("base_universe")
    def test_listing_devices_needs_a_session(self, client, session):
        assert client.get('/api/auth/tokens').status_code == 401
        assert client.delete('/api/auth/tokens').status_code == 401
        assert client.delete('/api/auth/token/1').status_code == 401


class TestTooManyDevices:

    @pytest.mark.usefixtures("base_universe")
    def test_the_oldest_goes_when_the_account_holds_too_many(
            self, client, session):
        """
        Un client qui redemande un jeton a chaque demarrage — parce qu'il le
        range mal, parce qu'il tourne dans un conteneur jetable — en
        accumulerait des milliers, tous valables.
        """
        signup(client)
        tokens = [get_token(client, device="poste %d" % n).json['token']
                  for n in range(MAX_PER_USER + 2)]

        alive = client.get('/api/auth/tokens').json['devices']

        assert len(alive) == MAX_PER_USER
        client.post('/api/auth/logout')
        assert client.post(
            '/api/auth/session', json={"token": tokens[0]}).status_code == 401
        assert client.post(
            '/api/auth/session', json={"token": tokens[-1]}).status_code == 200


class TestTheBrake:
    """
    Le frein des routes que l'on peut marteler.
    ---
    Ce n'est pas une barriere : il compte en memoire du processus, et deux
    ouvriers comptent chacun de leur cote. Ce qu'on eprouve ici est qu'il
    compte, qu'il rend 429 et qu'une reussite le vide — pas qu'il protege.
    """

    @pytest.mark.usefixtures("base_universe")
    def test_hammering_the_login_ends_in_a_refusal_to_answer(
            self, client, session):
        signup(client)

        codes = [get_token(client, password="faux").status_code
                 for _ in range(12)]

        assert 401 in codes
        assert codes[-1] == 429

    @pytest.mark.usefixtures("base_universe")
    def test_the_refusal_says_how_long_to_wait(self, client, session):
        signup(client)
        last = None
        for _ in range(12):
            last = get_token(client, password="faux")

        assert last.status_code == 429
        assert int(last.headers['Retry-After']) > 0

    @pytest.mark.usefixtures("base_universe")
    def test_a_success_clears_the_count(self, client, session):
        """
        Les essais qui precedent une reussite sont des fautes de frappe, pas une
        attaque : le joueur qui vient de trouver son mot de passe n'a aucune
        raison d'etre bloque au geste suivant.
        """
        signup(client)
        for _ in range(8):
            get_token(client, password="faux")

        assert get_token(client).status_code == 200
        assert get_token(client).status_code == 200

    @pytest.mark.usefixtures("base_universe")
    def test_signing_up_over_and_over_ends_in_a_refusal(self, client, session):
        codes = [signup(client, username="compte%d" % n,
                        email="c%d@testing.com" % n).status_code
                 for n in range(8)]

        assert 201 in codes
        assert codes[-1] == 429
