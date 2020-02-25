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
