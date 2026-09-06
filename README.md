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
* **In Docker — the reference way.** The suite runs against the pinned versions
  of `requirements.txt` (Python 3.7, SQLAlchemy 1.3.18, marshmallow 3.7.0), and
  a local interpreter with newer ones says nothing about what production will
  do — several of those pins no longer even install on Python 3.12.
  * `docker compose --profile test run --rm tests`
  * No database needed: the tests build their schema in an in-memory SQLite
    (`config/test.ini`), so the `db` service is not involved.
  * Narrow it down by passing pytest arguments:
    `docker compose --profile test run --rm tests python -m pytest tests/api/game/ships.py -q`
* On the host, if the pinned versions install on your interpreter
  * with virtualenv: `source venv/bin/activate`
  * with pipenv: `pipenv shell`
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
* Migration: a database that already holds territories needs the migration run
  (see **Database schema and migrations**), which adds the new columns and
  splits the old `mater` stock across iron/carbon/silicium.

## Ships and fleets
* A ship built at a planet shipyard **does not stay on the planet**. It leaves
  for the space of the system, where it belongs to a **fleet**: the fleet is
  what carries a position and takes orders, never the lone unit. The stock is
  still a count per type, but attached to a fleet instead of a territory.
* **Position** is client-side geometry. The server stores the Unity coordinates
  it is handed (`position_x/y/z`, system-local, orbital plane at `y = 0`) and
  gives them back untouched, so a fleet is found where it was left on the next
  entry into the system. Orbit radii and scale live entirely in the client.
* **Orbit is declared, never inferred.** `orbiting_territory_id` says which
  planet a fleet holds the orbit of. The server knows no planet coordinate and
  could not deduce it from a distance — yet this is what decides where a ship
  coming out of the shipyard goes.
* **Where a finished ship lands**, resolved at each delivery (see
  `Fleet.receive_construction` in `app/models/game/fleet.py`):
  * exactly **one** fleet in orbit — it takes the ship. The common case, and
    what the player expects: what is assembled joins what is already there;
  * **none** — one is created, in orbit of the planet that produced it;
  * **several** — the choice cannot settle itself, and picking one at random
    would decide in the player's stead. A fresh fleet collects the shipyard
    output; merging is the player's call, through `/api/fleet/<id>/transfer`.
  An order spans several units delivered over hours: the chosen fleet is noted
  on the event (`fleetId`) and reused, as long as it still holds that orbit —
  otherwise ten ships would create ten fleets.
* A **docked** fleet holds station over its planet, and planets revolve fast —
  up to thirty degrees a second, so the outer ones outrun a fleet. Docking is
  therefore a pursuit followed by station-keeping, not a trip to a fixed point,
  and a docked fleet's stored position goes stale as its world moves on. That is
  fine: on the next entry into the system it is the declared orbit that places
  it, not the coordinates.
* `POST /api/territory/<id>/ship` takes an optional `spawn` — `{x, y, z}`, the
  point where a fleet created by the server appears. Unity sends it, the web
  console does not (it has no scene); a fleet without one starts at the origin
  and Unity stores a position for it the first time it shows the system.
* Endpoints:
  * `GET /api/system/<id>/fleets` — the player's fleets, position and composition
  * `GET /api/system/<id>/army` — the same, summed per ship type
  * `POST /api/system/<id>/fleet` — create an empty fleet
  * `GET|POST|DELETE /api/fleet/<id>` — read, update (name, position, orbit),
    disband (empty fleets only)
  * `POST /api/fleet/<id>/position` — `{x, y, z}`, the hot path from Unity
  * `POST /api/fleet/<id>/orbit` — `{"territory_id": n}`, `null` or `0` detaches
  * `POST /api/fleet/<id>/transfer` — `{"to": n, "items": [{type, quantity}]}`
* `GET /api/territory/<id>/ships` **is gone**: ships are no longer a notion of
  the planet. Read them from the system, and recognise what holds a planet's
  orbit by each fleet's `orbiting_territory_id`.
* Migration: a database that already holds ships needs the migration run (see
  **Database schema and migrations**), which creates `fleet`, replaces
  `ship_territory` with `ship`, and pours each territory's stock into one fleet
  anchored in orbit of that territory. Migrated fleets start at the origin with
  no position: Unity gives them one the first time it shows the system.

## Database schema and migrations
* **Migrations grow an existing database, they do not create one.** The first
  revision of the chain (`04a2c6872769`) is a 2020 auto-export describing a
  schema the models no longer have — a `sector` table, a `system.sector_id`.
  Replaying the chain from scratch would not rebuild today's schema, it would
  build an obsolete one.
* A **fresh** database therefore comes out of `Base.metadata.create_all`
  (`initialize.py`, run by the container entrypoint), which then **stamps** it at
  the migration head so the chain takes over from there. Nothing else to do.
* An **existing** database is brought up with the migration command:
  * `docker compose --profile migrate run --rm migrate`
  * It is `python manage.py db upgrade` inside the app image, against the
    `db` service. On an up-to-date database it is a no-op.
  * On demand, never at startup: a migration moves data, and triggering that
    automatically — from several instances at once, no less — is the operator's
    call, not the application's.
* **At startup the application compares the two revisions** and logs a WARNING
  when they disagree. It does not refuse to start: an unreachable server is the
  last thing wanted at the moment one needs to connect and repair it. Three
  cases are reported:
  * *out of date* — the database is behind the code. The message carries both
    revisions and the command to run. Left alone, `create_all` will happily add
    the missing **tables** while no migration moves the **data** into them: the
    stocks stay behind in the old tables and the game looks emptied.
  * *unknown to this code* — the database was migrated by a newer checkout.
    Update the code, not the database.
  * *not under migration control* — tables are there but `alembic_version` is
    missing, so nothing can tell what is already applied. This is what databases
    created before the stamping look like. Pin them by hand at the revision
    matching their schema, then upgrade:
    ```
    docker compose --profile migrate run --rm migrate python manage.py db stamp c3e8f1a54d92
    docker compose --profile migrate run --rm migrate
    ```
* In development, `docker compose down -v` drops the volume and the next start
  builds a fresh, already-stamped database.

## Web UI (console)
* Served by the API itself, same origin, so the Flask-Login session cookie applies
* Open `http://localhost:9000/`
* Pick a galaxy on the sign-in screen, then one of your territories in it
* The galaxy lives in the URL (`/?galaxy=Milky+Way`): the link is shareable and
  reloadable, and switching galaxies works from the address bar as well as from
  the selector on the picker screen
* Screens: resource bar, orbit rail for the system, and the Buildings /
  Shipyard / Fleets / Orbital Defences panel with live construction progress
* The Fleets tab is where ships are found once assembled: each fleet with its
  composition, the orbit it holds and the Unity position the server kept — plus
  renaming, anchoring to the current orbit, disbanding an empty fleet, and
  transferring ships between fleets of the system
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
