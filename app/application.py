#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logger
import os
import optparse

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_paranoid import Paranoid
from flask_login import LoginManager, current_user
from functools import wraps
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.web.api.exceptions import APIException
from config.configuration import AppConfig

global db
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)
app.config['SECRET_KEY'] = 'the quick brown fox jumps over the lazy dog'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
login_manager = LoginManager(app)
paranoid = Paranoid(app)
paranoid.redirect_view = '/'
db = SQLAlchemy()


@app.errorhandler(APIException)
def handle_error(e):
    return jsonify({'message': str(e), 'statusCode': e.status_code}), e.status_code


@app.errorhandler(ValueError)
def handle_error(e):
    return jsonify({'message': str(e), 'statusCode': 400}), 400


# TODO test if it is a good solution to ensure territory is refresh after each access
'''
@app.after_request
def after_request_func(response):
    if 'territory' in request.url:
        args = request.view_args
        if 'territory_id' in args:
            print("need refresh on territory")
    return response
'''


@login_manager.user_loader
def load_user(username):
    from app.web.api.middleware import AuthUser

    return AuthUser(username=username)


def serialize(*args, **kwargs):
    to_give_at_serialize = kwargs

    def native_serializable(obj):
        try:
            jsonify(obj)
            return True
        except TypeError:
            return False

    def serialize_list(result):
        # On array results
        if len(result) > 0 and not hasattr(result[0], "serialize"):
            raise NotImplementedError("serialize property or function is not implemented")
        array_results = list()
        for r in result:
            if isinstance(r, list):
                serialized = serialize_list(r)
            elif isinstance(r, dict):
                serialized = serialize_dict(r)
            else:
                serialized = serialize_object(r)

            array_results.append(serialized)

        return array_results

    def serialize_dict(result):
        r_dict = {}
        for key, val in result.items():
            if native_serializable(val):
                serialized = val
            elif isinstance(val, list):
                serialized = serialize_list(val)
            elif isinstance(val, dict):
                serialized = serialize_dict(val)
            else:
                serialized = serialize_object(val)

            r_dict[key] = serialized
        return r_dict

    def serialize_object(result):
        if not hasattr(result, "serialize"):
            raise NotImplementedError(f"serialize property or function is not implemented on {type(result)}")
        if callable(result.serialize):
            if to_give_at_serialize:
                obj_serializable = result.serialize(**to_give_at_serialize)
            else:
                obj_serializable = result.serialize()
        else:
            obj_serializable = result.serialize

        if isinstance(obj_serializable, dict):
            obj_serializable = serialize_dict(obj_serializable)
        if isinstance(obj_serializable, list):
            obj_serializable = serialize_list(obj_serializable)

        return obj_serializable

    def _callable(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, list):
                # Array
                jsonable_result = serialize_list(result)
            elif isinstance(result, dict):
                # Dictionary
                jsonable_result = serialize_dict(result)
            # On simple result Object
            else:
                jsonable_result = serialize_object(result)
            return jsonify(jsonable_result)

        return wrapped

    if len(args) == 1 and callable(args[0]):
        return _callable(args[0])
    return _callable


def login_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                "message": "Not authorized"
            }), 401
        result = func(*args, **kwargs)
        return result
    return wrapped


def flaskrun(app, default_host="127.0.0.1", default_port="8080"):
    """
    Takes a flask.Flask instance and runs it. Parses
    command-line flags to configure the app.
    """
    LOGGER = logger.get_logger()

    # Set up the command-line options
    parser = optparse.OptionParser()
    parser.add_option("-H", "--host",
                      help="Hostname of the Flask app " +
                           "[default %s]" % default_host,
                      default=default_host)
    parser.add_option("-P", "--port",
                      help="Port for the Flask app " +
                           "[default %s]" % default_port,
                      default=default_port)

    # Two options useful for debugging purposes, but
    # a bit dangerous so not exposed in the help message.
    parser.add_option("-d", "--debug",
                      action="store_true", dest="debug",
                      help=optparse.SUPPRESS_HELP)
    parser.add_option("-p", "--profile",
                      action="store_true", dest="profile",
                      help=optparse.SUPPRESS_HELP)

    options, _ = parser.parse_args()

    # If the user selects the profiling option, then we need
    # to do a little extra setup
    if options.profile:
        from werkzeug.contrib.profiler import ProfilerMiddleware

        app.config['PROFILE'] = True
        app.wsgi_app = ProfilerMiddleware(
            app.wsgi_app,
            restrictions=[30]
        )
        options.debug = True

    db.init_app(app)
    engine = create_engine(AppConfig.get('database', 'uri'), echo=True)
    session_build = sessionmaker(bind=engine)
    session = session_build()
    from app.models.base import Base
    Base.metadata.create_all(engine)
    app.run(
        debug=options.debug,
        host=options.host,
        port=int(options.port)
    )
