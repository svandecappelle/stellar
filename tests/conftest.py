import sys
import os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from run import create_app
from app.application import db
from config.configuration import AppConfig
from app.models import Base, User
from app.models.role import RoleType


@pytest.fixture(autouse=True, scope='function')
def flask_app():
    flask_app = create_app(environment="test")
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    engine = create_engine(AppConfig.get('database', 'uri'), echo=False)
    session_build = sessionmaker(bind=engine)
    session = session_build()
    db.session = session
    Base.metadata.create_all(bind=engine)
    session.commit()
    yield flask_app, session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope='function')
def session(flask_app):
    return flask_app[1]


@pytest.fixture(scope='function')
def client(flask_app):
    # Flask provides a way to test your application by exposing the Werkzeug test Client
    # and handling the context locals for you.
    testing_client = flask_app[0].test_client()

    # Establish an application context before running the tests.
    ctx = flask_app[0].app_context()
    ctx.push()
    yield testing_client
    # ctx.pop()


@pytest.fixture(name="authentify")
def login(client, allowed_users):
    def auth(user_to_authenticate=allowed_users[0]):
        with client.session_transaction() as session:
            response = client.post(
                '/api/auth/login',
                json={
                    "username": user_to_authenticate["username"],
                    "password": user_to_authenticate["password"],
                    "remember_me": True
                })
            assert response.status_code == 200
    return auth


@pytest.fixture(name="allowed_users")
def users(session):
    users_to_create = [{
        "username": "admin",
        "password": "admin",
        "email": "test@testing.com"
    }]
    for usr in users_to_create:
        user = User.new(
            username=usr['username'],
            password=usr['password'],
            email=usr['email']
        )
        user.add_role(RoleType.admin)
    session.commit()
    return users_to_create


@pytest.fixture(scope="function", name="authenticate_as_admin")
def authenticate_as_admin(allowed_users, authentify):
    authentify(allowed_users[0])
