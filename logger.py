import traceback
import logging
import sys

from logging_gelf.formatters import GELFFormatter
from flask import has_request_context, request

global logger
logger = None

def get_logger(config=None):
    global logger
    if logger is None:
        logger = DefaultLogger(config)
    return logger



class DefaultLogger(object):
    def __init__(self, config=None, extra={}):
        self.logger = logging.getLogger(config.get("logging", "name"))
        level = logging.getLevelName(config.get('logging', 'level') or 'INFO')
        # on met le niveau du logger à DEBUG, comme ça il écrit tout
        self.logger.setLevel(level)

        # création d'un formateur qui va ajouter le temps, le niveau
        # de chaque message quand on écrira un message dans le log
        FORMAT = '%(asctime)s :: %(levelname)s :: %(message)s'
        self.extra = extra

    def _feed_kwargs(self, kwargs):
        extra = {}
        extra.update(self.extra)
        if 'extra' in kwargs:
            extra.update(kwargs['extra'])
        kwargs['extra'] = extra

    def _log(self, method, *args, **kwargs):
        if "exception" in kwargs:
            exception = kwargs.pop("exception")
            kwargs.setdefault("extra", {})
            kwargs['extra']['exception'] = exception
            kwargs['extra']['exception_message'] = exception
            kwargs['extra']['exception_tb'] = traceback.format_tb(sys.exc_info()[2])
            kwargs['exc_info'] = True
            self.logger.exception(exception)
        return getattr(self.logger, method)(*args, **kwargs)

    def debug(self, *args, **kwargs):
        self._feed_kwargs(kwargs=kwargs)
        return self._log("debug", *args, **kwargs)

    def info(self, *args, **kwargs):
        self._feed_kwargs(kwargs=kwargs)
        return self._log("info", *args, **kwargs)

    def warn(self, *args, **kwargs):
        self._feed_kwargs(kwargs=kwargs)
        return self._log("warn", *args, **kwargs)

    def error(self, *args, **kwargs):
        self._feed_kwargs(kwargs=kwargs)
        return self._log("error", *args, **kwargs)

    def critical(self, *args, **kwargs):
        self._feed_kwargs(kwargs=kwargs)
        return self._log("critical", *args, **kwargs)
