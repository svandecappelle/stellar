#!/usr/bin/env python
# -*- coding: utf-8 -*-

from run import Starter, create_app

app = create_app()

# Sous gunicorn, personne ne passe par `Starter.launch` : le controle du schema
# se ferait donc nulle part, et une base en retard ne se signalerait qu'a la
# premiere colonne manquante, en pleine partie.
Starter.check_schema()

if __name__ == "__main__":
    print("wsgi run...")
    app.run()