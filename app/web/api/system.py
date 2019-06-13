# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, abort, Response, redirect, jsonify
from app.application import APP as app
from app.application import login_required
import requests
import json
import os
from app.cache import CACHE_RESPONSES
from config import AppConfig
import logger
