#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import importlib
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application import app, db, dburi, flaskrun
from app.models.base import Base
from app.models.game.galaxy import Galaxy
from app.models.user import User
from app.models.role import RoleType
from app.settings.logger import LoggerConfigurator
from config.configuration import AppConfig

env = os.getenv('ENV', 'prod')
ROUTES_FOLDERS = ["app/web"]


def walk(directory, only_regular_files=True):
    out = []
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in files:
            out.append(os.path.join(root, name))
        if not only_regular_files:
            for name in dirs:
                out.append(os.path.join(root, name))
    return out


class Starter(object):
    """
    Application entry point stating utilities
    """

    @classmethod
    def configure(cls, config_file=None):
        cls.logger = logging.getLogger('Starter')
        cls.logger.info("[%s] configuring..." % config_file)
        AppConfig.load(config_file=config_file)
        LoggerConfigurator.configure()
        app.config['SQLALCHEMY_DATABASE_URI'] = dburi()
        cls.routing()

    @classmethod
    def routing(cls):
        """Routing application"""
        for route_folder in ROUTES_FOLDERS:
            cls.logger.info("[%s] Route importing..." % route_folder)
            modules = walk(route_folder)
            for module in modules:
                if module.endswith('.py') and not module.endswith('__init__.py'):
                    route_file = re.sub(r'/', r'.', module)
                    route_file = re.sub(r'\\', r'.', route_file)
                    route_file = route_file[:-3]
                    cls.logger.info("[%s] Route importing..." % route_file)
                    importlib.import_module(route_file)
                    cls.logger.info("[%s] imported" % route_file)

    @classmethod
    def launch(cls):
        """Launch api server"""
        cls.logger.info("Starting server")
        flaskrun(app,default_host="0.0.0.0", default_port="9000")

    @classmethod
    def status(cls):
        """Check starting status"""

    @classmethod
    def stop(cls):
        """Stop api server"""


def create_app(environment=None):
    Starter.configure(config_file=os.getenv("CONFIG") or environment)
    return app


def main():
    """Entry point"""
    Starter.configure(config_file=os.getenv("CONFIG") or env)
    Starter.launch()


if __name__ == '__main__':
    print("Starting server...")
    main()



"""
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
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
"""