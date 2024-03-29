#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import importlib
import re

from config.configuration import AppConfig
from app.application import app, dburi, flaskrun
from app.settings.logger import LoggerConfigurator

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
    Memsource proxifier application entry point
    """

    @classmethod
    def configure(cls, config_file=None):
        AppConfig.load(config_file=config_file)
        LoggerConfigurator.configure()
        app.config['SQLALCHEMY_DATABASE_URI'] = dburi()
        cls.logger = logging.getLogger('MemsourceProxifier')
        cls.routing()

    @classmethod
    def routing(cls):
        """Routing application"""
        for route_folder in ROUTES_FOLDERS:
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
        flaskrun(app)

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
    """Enty point"""
    Starter.configure(config_file=os.getenv("CONFIG") or env)
    Starter.launch()


if __name__ == '__main__':
    main()
