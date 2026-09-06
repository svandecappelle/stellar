from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from run import create_app
from app.application import db, dburi
from config.configuration import AppConfig
from app.models.base import Base
from app.models.game.galaxy import Galaxy
from app.models.user import User
from app.models.role import RoleType
from logger import get_logger
import schema_version


def stamp_head(engine):
    """
    Marquer une base neuve a la tete de la chaine de migrations.

    Sans ce tampon, `alembic_version` reste absent et rien ne dit qu'un schema
    fraichement bati est deja a jour : la prochaine migration repartirait du
    debut de la chaine, dont la premiere revision est un export de 2020 decrivant
    un schema que les modeles n'ont plus. Elle echouerait sur des tables deja la,
    et dans le meilleur des cas ne ferait rien.

    Ce n'est pas un raccourci : une base que `create_all` vient de batir porte
    par construction le schema des modeles, donc celui de la tete. Le tampon ne
    fait que l'ecrire.
    """
    head = schema_version.head_revision()
    if head is None:
        return

    engine.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version "
        "(version_num VARCHAR(32) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))")
    engine.execute("DELETE FROM alembic_version")
    engine.execute("INSERT INTO alembic_version (version_num) VALUES ('%s')" % head)
    get_logger().info(
        "Fresh database stamped at the migration head", infos=dict(revision=head))


if __name__ == '__main__':
    environment = os.getenv('CONFIG', 'prod')
    flask_app = create_app(environment=environment)
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    engine = create_engine(dburi(), echo=False)
    session_build = sessionmaker(bind=engine)
    session = session_build()
    db.session = session

    # Avant `create_all` : c'est le seul moment ou l'on distingue une base neuve
    # d'une base deja peuplee. Apres, les tables existent dans les deux cas et
    # la question ne se pose plus.
    state, current, head = schema_version.status(engine)

    Base.metadata.create_all(bind=engine)
    session.commit()

    if state == schema_version.UNKNOWN and current is None:
        # Base vide : `create_all` vient d'en batir le schema courant, on le dit.
        stamp_head(engine)
    else:
        # Base deja la : `create_all` a pu y ajouter les tables manquantes, mais
        # il ne deplace aucune donnee et n'en retire aucune. Une migration reste
        # necessaire, et c'est elle qui portera les stocks d'un schema a l'autre.
        schema_version.warn_if_outdated(engine)

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
