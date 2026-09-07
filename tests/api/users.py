import pytest


class TestUsers:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_get_current_user_by_name(self, client, session):
        """
        Check if user can be retrieve
        ---
        :param client: http client
        :param session: db session
        """
        response = client.get("/api/user/admin")
        assert response.status_code == 200
        assert response.json['username'] == "admin"
        assert response.json.get('roles') is None

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_get_current_user_with_roles(self, client, session):
        """
        Check if user can be retrieve
        ---
        :param client: http client
        :param session: db session
        """
        response = client.get("/api/auth")
        assert response.status_code == 200
        assert response.json['username'] == "admin"
        assert response.json.get('roles') is not None
        assert len(response.json.get('roles')) == 1


class TestLogout:

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_logout_really_ends_the_session(self, client, session):
        """
        Se deconnecter deconnecte.
        ---
        La route posait `logged_in = False`, un drapeau que personne ne lit, et
        ne touchait pas a la session de Flask-Login : le joueur restait
        authentifie, et la console qui affichait l'ecran de connexion mentait.

        On verifie donc l'effet, pas l'appel : une route protegee doit refuser
        apres coup.
        """
        assert client.get('/api/auth').status_code == 200

        response = client.post('/api/auth/logout')
        assert response.status_code == 200

        assert client.get('/api/auth').status_code == 401

    @pytest.mark.usefixtures("authenticate_as_admin")
    def test_logout_clears_the_session_cookie(self, client, session):
        """
        La session ne doit plus rien porter apres coup.
        ---
        Le cookie survivait a la deconnexion, et c'est par lui que la session
        repartait. On regarde ce qu'il reste cote serveur : la cle d'identite de
        Flask-Login doit avoir disparu.
        """
        client.post('/api/auth/logout')

        with client.session_transaction() as sess:
            assert '_user_id' not in sess
            assert 'logged_in' not in sess


class TestRaiseUsers:
    def test_raise_get_user_by_name_not_authenticated(self, client, session):
        """
        Check if user cause 401 not authorized when not authenticated
        ---
        :param client: http client
        :param session: db session
        """
        response = client.get("/api/user/admin")
        assert response.status_code == 401
