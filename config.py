import sys

import os
import logging
import configparser
import logger

VAULT_KEY_FORMAT = 'digital-tools-channel/{}'


class IncompleteConfig(Exception):
    """
    Raised when config was incomplete
    """
    pass


class AppConfig:
    _config = None
    logger = logging.getLogger('ProxyConfiguration')

    @classmethod
    def load(cls, config_file=None):
        cls._retrieve_config_from_file(filename=config_file)
        cls.initialized = True

    @classmethod
    def get(cls, section, key):
        return cls._config.get(section, key)

    @classmethod
    def get_boolean(cls, section, key):
        return cls._config.getboolean(section, key)

    @classmethod
    def _retrieve_config_from_file(cls, filename):
        cls._config = configparser.ConfigParser()
        filename = "./config/{}.ini".format(filename)
        if not cls._config.read(filename):
            raise IncompleteConfig("cannot read file {}".format(filename))
