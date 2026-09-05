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

## Resources and planet archetypes
* Twelve resources. Eight are **materials** pulled out of the ground —
  `iron`, `carbon`, `silicium`, `titanium`, `cristal`, `uranium`, `hydrogen`,
  `neutronium` — the other four (`credits`, `energy`, `population`, `tritium`)
  come from a dedicated building and exist everywhere.
* There is a **single** `mater_extractor`. What it produces is decided by the
  territory, not by the building: a gas giant yields hydrogen and nothing else,
  whatever its level.
* Each territory is drawn a **`PlanetArchetype`** at creation (server-side, see
  `app/models/game/planet.py`). The archetype sets which materials exist there
  and their base ratios; a per-territory **deposit roll** then varies richness
  by ±25%, with a 12% chance of a rich vein doubling one material.
* Neutronium comes only from `anomaly` worlds, ~1% of territories: it gates the
  Mother Ship, the Orbital Station and the `distorsion` technology.
* `GET /api/territory/<id>` exposes `archetype`, `archetype_label`, the raw
  `deposits` and the applied `yields`. `GET /api/catalog` lists every archetype
  with its yield table.
* Territories are scoped to a galaxy through their system, so every serialized
  territory carries `galaxy_name` at the root, and the list is read per galaxy:
  * `GET /api/galaxy/<name>/territories` — the player's territories in that
    galaxy. This is the one to use inside a galaxy.
  * `GET /api/galaxy/<name>/free-system` — a randomly picked system where no
    player holds anything. Used to seat a new player: they enter it and the
    client settles a telluric world there. Nothing is reserved, so two players
    served at once can get the same system; the territory claim settles it.
  * `GET /api/territories` — every territory the player holds, all galaxies
    mixed. Only for the question a galaxy cannot answer: where does this
    player own anything at all?
* Migration: the schema is normally created by `Base.metadata.create_all`
  (`initialize.py`), so a **fresh** database needs nothing. A database that
  already holds territories needs `alembic upgrade head`, which adds the new
  columns and splits the old `mater` stock across iron/carbon/silicium. In dev,
  `docker compose down -v` is the shortcut.

## Web UI (console)
* Served by the API itself, same origin, so the Flask-Login session cookie applies
* Open `http://localhost:9000/`
* Pick a galaxy on the sign-in screen, then one of your territories in it
* The galaxy lives in the URL (`/?galaxy=Milky+Way`): the link is shareable and
  reloadable, and switching galaxies works from the address bar as well as from
  the selector on the picker screen
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
