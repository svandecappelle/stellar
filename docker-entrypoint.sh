#!/bin/bash

GUNICORN_CMD_ARGS="--bind=0.0.0.0:9000" gunicorn --thread 4 wsgi:app
