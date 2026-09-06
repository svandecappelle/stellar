import traceback
import logging
import sys

from logging_gelf.formatters import GELFFormatter
from logging_gelf.schemas import GelfSchema
from flask import has_request_context, request
from marshmallow import fields

#: Le logger reel, construit au premier appel de `get_logger`.
_logger = None


def get_logger(config={}):
    global _logger
    if _logger is None:
        _logger = DefaultLogger(config)
    return _logger


class LazyLogger(object):
    """
    Le logger vu par `from logger import logger`, resolu a l'appel.

    La variable de module valait None au chargement, et `from logger import
    logger` figeait ce None chez l'importateur : reaffecter la globale depuis
    `get_logger` ne remontait pas jusqu'a lui. Tout module charge avant le
    premier `get_logger()` se retrouvait donc avec None, et levait un
    AttributeError des la premiere ligne de journal. C'est le cas de tous les
    modeles sous pytest — conftest les importe avant de creer l'application —
    et c'est pourquoi la moindre construction y rendait une erreur 500.

    Passer par un objet qui delegue supprime la question : il n'y a plus de
    valeur a figer, seulement une resolution au moment ou l'on journalise.
    """

    def __getattr__(self, name):
        return getattr(get_logger(), name)


logger = LazyLogger()

class MyGelfSchema(GelfSchema):
    infos = fields.Str()
    user_id = fields.Str()

class DefaultLogger(object):
    def __init__(self, config={}, extra={}):
        self.logger = logging.getLogger(config.get("logging", "name"))
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(GELFFormatter(schema=MyGelfSchema))
        self.logger.addHandler(handler)
        # level = logging.getLevelName(config.get('logging', 'level') or 'INFO')
        # self.logger.setLevel(level)

    def _log(self, method, *args, **kwargs):
        kwargs.setdefault("extra", {})
        if "exception" in kwargs:
            exception = kwargs.pop("exception")
            kwargs['extra']['exception'] = exception
            kwargs['extra']['exception_message'] = exception
            kwargs['extra']['exception_tb'] = traceback.format_tb(sys.exc_info()[2])
            kwargs['exc_info'] = True
            self.logger.exception(exception)
        if "infos" in kwargs:
            kwargs['extra']['infos'] = kwargs.pop("infos")
        return getattr(self.logger, method)(*args, **kwargs)

    def debug(self, *args, **kwargs):
        return self._log("debug", *args, **kwargs)

    def info(self, *args, **kwargs):
        return self._log("info", *args, **kwargs)

    def warn(self, *args, **kwargs):
        return self._log("warn", *args, **kwargs)

    def error(self, *args, **kwargs):
        return self._log("error", *args, **kwargs)

    def critical(self, *args, **kwargs):
        return self._log("critical", *args, **kwargs)
