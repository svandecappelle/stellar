# -*- coding: utf-8 -*-

"""
Commandes de migration du schema.

    python manage.py db upgrade
    python manage.py db downgrade
    python manage.py db revision --autogenerate -m "..."

Ce que cela remplace : `Flask-Script`, abandonne en 2017 et incompatible avec
Flask 2 — il en attendait un `app.instance_path` et un contexte de commande qui
n'existent plus. Flask-Migrate expose desormais ses commandes directement dans
l'interface de Flask (`flask db ...`), et on les appelle ici a travers elle.

L'invocation reste `python manage.py db <commande>` : c'est ce qu'ecrivent le
docker-compose, la documentation et les habitudes. Rien de tout cela n'a a
changer parce qu'une dependance a disparu.
"""

import importlib
import os
import sys

from flask_migrate import Migrate

from run import create_app
from app.application import db

MODELS_DIRECTORY = "app/models"
EXCLUDE_FILES = ["__init__.py"]


def import_models():
    """
    Charge tous les modeles.

    Alembic compare le schema aux tables declarees : un modele qui n'a pas ete
    importe n'a pas de table enregistree dans les metadonnees, et une migration
    generee sans lui proposerait de supprimer sa table.
    """
    for dir_path, _, file_names in os.walk(MODELS_DIRECTORY):
        for file_name in file_names:
            if file_name.endswith("py") and file_name not in EXCLUDE_FILES:
                module_path, _ = os.path.splitext(os.path.join(dir_path, file_name))
                importlib.import_module(module_path.replace(os.sep, "."))


def main():
    app = create_app(environment=os.getenv('ENV', 'prod'))
    Migrate(app, db)
    import_models()

    # `flask db ...` sans passer par la variable d'environnement FLASK_APP :
    # l'application est deja construite, on lui donne simplement la main.
    return app.cli.main(args=sys.argv[1:], standalone_mode=False)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - la commande rend son propre message
        print(error, file=sys.stderr)
        sys.exit(1)
