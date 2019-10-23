#!/usr/bin/env python
# -*- coding: utf-8 -*-

import platform
import logging
from logging.handlers import RotatingFileHandler

from config import AppConfig
from logger import get_logger
from logging_gelf.formatters import GELFFormatter


from marshmallow import fields
from logging_gelf.schemas import GelfSchema


class FormatterSchema(GelfSchema):
    request_id = fields.String()
    internal_request_id = fields.String()


class LoggerConfigurator:
    """default system logger configurator"""

    @classmethod
    def configure(cls):
        # création de l'objet logger qui va nous servir à écrire dans les logs
        logger = get_logger(config=AppConfig)

        ch = logging.StreamHandler()
        if AppConfig.get_boolean('logging', 'gelf'):
            FORMAT = GELFFormatter(schema=FormatterSchema, null_character=True)
        else:
            FORMAT = '%(asctime)s :: %(levelname)s :: %(message)s'
        ch.setFormatter(FORMAT)

        # création d'un handler qui va rediriger une écriture du log vers
        # un fichier en mode 'append', avec 1 backup et une taille max de 1Mo
        file_handler = RotatingFileHandler('activity.log', 'a', 1000000, 1)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s'))

        logger.logger.addHandler(file_handler)
        logger.logger.addHandler(ch)
