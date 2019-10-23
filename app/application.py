#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logger
import os
import optparse

from flask import Flask, session, request, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.exceptions import Forbidden

from config import AppConfig
from app.models.base import Base

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

global db
app.config['SECRET_KEY'] = 'the quick brown fox jumps over the lazy dog'

db = SQLAlchemy()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
        if not session or not session['logged_in']:
            return jsonify({
                "message": "Not authorized"
            }), 401
        return f(*args, **kwargs)
    return decorated_function


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
    Session = sessionmaker(bind=engine)
    session = Session()
    Base.metadata.create_all(engine)
    app.run(
        debug=options.debug,
        host=options.host,
        port=int(options.port)
    )
