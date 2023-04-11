from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from run import create_app
from app.application import db, dburi
from config.configuration import AppConfig
from app.models.base import Base
from app.models.game.galaxy import Galaxy
from app.models.user import User
from app.models.role import RoleType

if __name__ == '__main__':
    flask_app = create_app(environment="prod")
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    engine = create_engine(dburi(), echo=False)
    session_build = sessionmaker(bind=engine)
    session = session_build()
    db.session = session
    Base.metadata.create_all(bind=engine)
    session.commit()
    if not Galaxy.exists(session=session, name="Milky Way"):
        Galaxy.create(session=session, name="Milky Way")
    if not User.exists(username="admin"):
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
