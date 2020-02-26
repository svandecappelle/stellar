#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logger
import os
import optparse

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_paranoid import Paranoid
from flask_login import LoginManager, current_user
from functools import wraps
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.exceptions import Forbidden

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


@login_manager.user_loader
def load_user(username):
    from app.web.api.middleware import AuthUser

    return AuthUser(username=username)


def serialize(*args, **kwargs):
    to_give_at_serialize = kwargs

    def _callable(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            result = func(*args, **kwargs)
            if not hasattr(result, "serialize"):
                raise NotImplementedError("serialize property or function is not implemented")
            if callable(result.serialize):
                if to_give_at_serialize:
                    return jsonify(result.serialize(**to_give_at_serialize))
                return jsonify(result.serialize())
            return jsonify(result.serialize)
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
