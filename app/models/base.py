import inspect
import sys
import logging
import simplejson as json
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import object_session
from sqlalchemy.types import UserDefinedType
from flask_jsontools import JsonSerializableBase
# SQLITE cant do autoincrement on bigint so we need this hybrid type
from sqlalchemy.dialects import sqlite

from .exceptions import CheckError, CheckErrorWithCode


Base = declarative_base(cls=(JsonSerializableBase,))
metadata = Base.metadata

BigIntLite = BigInteger()
BigIntLite = BigIntLite.with_variant(sqlite.INTEGER, 'sqlite')


class JsonSQLite(UserDefinedType):
    """
    Only used for testing, JSON to TEXT
    """

    def get_col_spec(self, **kw):
        return "TEXT"

    def bind_processor(self, dialect):
        def process(value):
            return json.dumps(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return json.loads(value)

        return process


Json = JSONB()
Json = Json.with_variant(JsonSQLite, 'sqlite')


def get_logger():
    """
    Get default logger
    """
    return logging.getLogger('Base')


def get_check_funcs(name, ignored_funcs=[]):
    return [obj for name, obj in inspect.getmembers(sys.modules[name])
            if (inspect.isfunction(obj) and
                name.startswith('check_') and name not in ignored_funcs)]


def _process_check_error(check, errors, e, model):
    if isinstance(e, CheckErrorWithCode):
        get_logger().error("{} check failed: {}".format(check.__name__, e.verbose_message()), extra={
            'check_failed': check.__name__,
            'check_failed_model': model.__class__.__name__,
            'check_failed_model_value': model.as_dict(),
            'check_failed_message': e.verbose_message(),
        })
    else:
        get_logger().error('{} check failed: {}'.format(check.__name__, e.message),
                           extra={'check_failed': check.__name__,
                                  'check_failed_model': model.__class__.__name__,
                                  'check_failed_message': e.message,
                                  'check_failed_model_value': model.as_dict()})
    errors.append(e)


def is_valid(self, session, ignored_checks=[]):
    errors = []
    error_codes = []
    path_checks = get_check_path(self._module_name)

    try:
        __import__(path_checks)
    except ImportError:  # pragma: no cover
        return True  # pragma: no cover

    checks = get_check_funcs(name=path_checks, ignored_funcs=ignored_checks)

    if not checks:
        return True

    for check in checks:
        try:
            check(self, session)
        except CheckError as e:
            _process_check_error(check=check, errors=errors, e=e, model=self)
        except CheckErrorWithCode as e:
            _process_check_error(check=check, errors=error_codes, e=e, model=self)
        except CheckErrorMultipleCodes as e:
            for error in e.errors:
                _process_check_error(check=check, errors=error_codes, e=error, model=self)
    if errors:
        raise CheckError(errors)
    return True


def as_dict(self):
    """ Override in each model if you need to load any relationship not in columns """
    return {c.name: getattr(self, c.name) for c in self.__table__.columns}


Base.is_valid = is_valid
Base.as_dict = as_dict
Base.to_dict = as_dict  # TODO change to_dict -> as_dict in all the models


def get_check_path(name):
    return '{}_checks'.format(name.replace('.models.', '.models.checks.'))


def compare(self, other, attrs=None, exclude_attrs=None):
    """
    Compare to another instance of the same type.
    You can specify attributes to take into account (attrs) or to exclude (exclude_attrs)
    Returns None if no difference or a dict with this format:
        {
            'attr1': [ value1_in_self, value1_in_other ],
            'attr2': [ value2_in_self, value2_in_other ], ...
        }
    """
    if self.__class__.__name__ != other.__class__.__name__:
        raise TypeError('Cannot compare instances of different type: {} vs {}'
                        .format(self.__class__.__name__, other.__class__.__name__))

    result = {}
    attrs = list(set(attrs)) if attrs else [x.name for x in self.__table__.columns]
    if exclude_attrs:
        attrs = [x for x in attrs if x not in exclude_attrs]

    for attr in attrs:
        attr_value, other_attr_value = [x.__getattribute__(attr) for x in (self, other)]
        if attr_value != other_attr_value:
            result[attr] = {
                'new_value': attr_value,
                'original_value': other_attr_value,
            }

    return result if result else None


Base.compare = compare


def __getitem__(self, key):
    return getattr(self, key)


# To be able to do model['id'] while Celery does not have access to database directly
Base.__getitem__ = __getitem__


def __repr__(self):
    if hasattr(self, "id"):
        return "<{}#{}>".format(self.__class__.__name__, self.id)
    return "<{}>".format(self.__class__.__name__)


def __json_serializable__(self):
    if hasattr(self, "serialize"):
        return self.serialize
    raise Exception("Not JSON serializable")


Base.__repr__ = __repr__
Base.__json_serializable__ = __json_serializable__


class HasMetadata(object):
    def set_metadata(self, key, value):
        """
        Define the metadata for current object
        :param key: Metadata key
        :type key: string
        :param value: Metadata value
        :type value: value
        :return: Metadata created or updated
        """
        md = self.get_metadata(key=key)
        if md:
            md.value = value
        else:
            md = self._metadata_class(key=key, value=value)
            self.meta_data.append(md)
        return md

    def get_metadata(self, key):
        """
        Finds the first metadata with key
        :param key: Key lookup
        :type key: string
        :return: Metadata found, or None if not found
        """
        for md in self.meta_data:
            if md.key == key:
                return md
        return None

    def has_metadata(self, key):
        """
        Returns whether the current object has a metadata with this key
        :param key: Metadata key
        :type key: string
        :return: True if the current object has a metadata with this key
        :rtype: bool
        """
        return bool(self.get_metadata(key=key))

    def remove_metadata(self, key):
        """
        Removes the metadata, raising an error if it does not exist
        :param key: Metadata key
        :type key: string
        """
        md = self.get_metadata(key=key)
        if not md:
            raise ValueError("Metadata {} not found".format(key))
        self.meta_data.remove(md)
        object_session(self).delete(md)
