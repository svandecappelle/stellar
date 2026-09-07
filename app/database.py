# -*- coding: utf-8 -*-

"""
Le porteur de session de l'application.

Ce qu'il remplace : `Flask-SQLAlchemy`, dont il ne restait ici qu'une coquille.
Le paquet n'etait utilise que pour trois choses — `db.session`, `db.init_app` et
`db.metadata` — jamais pour ce qui fait son interet : ni `db.Model`, ni
`db.Column`, ni `db.create_all`. L'application construit son moteur et sa
session elle-meme (voir `initialize.py`, `run.py`, `tests/conftest.py`) puis les
pose ici.

C'est aussi ce qui interdisait la montee de version. Depuis Flask-SQLAlchemy 3,
`session` est une propriete en lecture seule, calculee par l'extension : les
quatre-vingt-six appels a `db.session` du projet reposent au contraire sur une
session que l'application affecte a la main. Garder le paquet aurait donc
demande de repenser toute la gestion de session ; le retirer ne demande que ces
quelques lignes.

`metadata` designe celle des modeles : c'est par elle que Flask-Migrate compare
le schema aux tables, via `current_app.extensions['migrate'].db.metadata`.
"""


class Database(object):
    """Session courante et metadonnees des modeles, pour toute l'application."""

    def __init__(self):
        #: Session posee explicitement par l'appelant, s'il y en a une.
        self._session = None
        #: Session de secours, construite a la demande. Voir `session`.
        self._scoped = None
        self._engine = None
        self._app = None

    @property
    def session(self):
        """
        La session a utiliser.

        Deux regimes, et il a fallu se bruler pour le comprendre : `initialize.py`
        et les tests posent leur propre session — sur une transaction a annuler,
        pour les seconds — tandis que le processus qui sert n'en pose aucune. Il
        s'en remettait entierement a Flask-SQLAlchemy, qui lui en fabriquait une.
        Rendre `None` dans ce cas mettait l'API a genoux : toute lecture de
        modele echouait en 500.

        La session de secours est donc `scoped` : le serveur de developpement
        sert plusieurs requetes de front, et une session unique partagee entre
        fils melangerait leurs transactions.
        """
        if self._session is not None:
            return self._session

        if self._scoped is None:
            from sqlalchemy.orm import scoped_session, sessionmaker

            self._scoped = scoped_session(sessionmaker(bind=self.engine))

        return self._scoped

    @session.setter
    def session(self, value):
        self._session = value

    @property
    def engine(self):
        """
        Le moteur de la session de secours, construit a la demande.

        A la demande et non a la construction : ce module est charge avant que
        la configuration ne soit lue, et l'adresse de la base n'est pas encore
        connue a ce moment-la.
        """
        if self._engine is None:
            from sqlalchemy import create_engine

            from app.application import dburi

            self._engine = create_engine(dburi())

        return self._engine

    @property
    def metadata(self):
        """
        Les metadonnees des modeles.

        Resolue a la demande et non a la construction : ce module est importe
        avant les modeles, et remonter la chaine ici ferait une boucle
        d'imports. C'est par elle que Flask-Migrate compare le schema aux
        tables, via `current_app.extensions['migrate'].db.metadata`.
        """
        from app.models.base import Base

        return Base.metadata

    def release(self):
        """
        Rend la session de secours au bout d'une requete.

        Ce menage est celui que faisait Flask-SQLAlchemy. Sans lui, une session
        `scoped` garde son cache d'objets d'une requete a l'autre : deux lectures
        successives du meme enregistrement rendraient la premiere version, et une
        modification faite ailleurs resterait invisible.

        Sans effet quand une session a ete posee a la main — c'est alors a son
        proprietaire d'en decider, et les tests comptent justement sur la leur
        pour survivre a la requete.
        """
        if self._session is None and self._scoped is not None:
            self._scoped.remove()

    def init_app(self, app):
        """
        Rattache l'application.

        Rien n'est enregistre ici. Le menage de fin de requete l'est une fois
        pour toutes a la creation de l'application (`app/application.py`) :
        Flask 3 refuse tout gestionnaire pose apres la premiere requete servie,
        et cette methode-ci est rappelee a chaque test sur une application qui,
        elle, ne change pas.
        """
        self._app = app
        return self

    @property
    def app(self):
        return self._app
