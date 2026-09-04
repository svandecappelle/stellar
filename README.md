# stellar

[![codecov](https://codecov.io/gh/svandecappelle/stellar/branch/master/graph/badge.svg?token=124Z4FDYF2)](https://codecov.io/gh/svandecappelle/stellar)

## Installation
* using virtualenv
  virtualenv --python=3.8 venv
  pip install -r requirements.txt
* using pipenv
  pipenv --python 3.8
  pipenv install --dev

## Running tests
* with virtualenv
  * activate virtual environment: `source venv/bin/activate`
* with pipenv
  * activate virtual environment: `pipenv shell`
* `pytest tests`

## Running with Docker Compose
* start API + PostgreSQL
  * `docker compose up --build`
* API is available on `http://localhost:9000`
* stop stack
  * `docker compose down`
* stop stack and remove database volume
  * `docker compose down -v`

## Web UI (console)
* Served by the API itself, same origin, so the Flask-Login session cookie applies
* Open `http://localhost:9000/`
* Sign in with a game account, then pick one of your territories
* Screens: resource bar, orbit rail for the system, and the Buildings /
  Shipyard / Orbital Defences panel with live construction progress
* Three visual directions ship together (Nebula Grid, Admiralty, Drydock);
  the switcher sits in the top bar and the choice is kept in `localStorage`
* Sources are plain HTML/CSS/ES modules under `app/static` — no build step:
  * `css/tokens.css` — one token set per direction
  * `css/components.css` — shared component library, reads only tokens
  * `js/api.js`, `js/app.js`, `js/icons.js`

## API Documentation (Swagger UI)
* Open Swagger UI at `http://localhost:9000/api/docs`
* Open raw OpenAPI spec at `http://localhost:9000/api/openapi.json`

## Update OpenAPI Schema File
* Generate a schema file that matches the current Flask routes:
  * `python update_openapi_schema.py --routes-root app/web/api --app-web-root app/web --output app/web/api/openapi.generated.json`
