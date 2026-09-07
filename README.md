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
* Tritium exists everywhere, but not in the same quantity: the `rafinery`
  draws it from the **water** of the world. Each archetype carries a `water`
  percentage, and the multiplier it yields runs from 0.62 on a desert to 1.60
  on an oceanic — 1.20 on the telluric world every player starts from. It never
  reaches zero: a world cut off from its only tritium source would be
  unplayable, a dry one is merely a poor place to refine.
* Buildings, technologies, ships and defenses are **paid for when ordered**,
  not when delivered. An order for N units costs N times the unit price.
  Energy and population are required but never consumed: energy is a balance
  recomputed from the power station minus what the buildings draw, and
  population mans the batteries rather than being burnt by them.
* `GET /api/territory/<id>` exposes `archetype`, `archetype_label`, the raw
  `deposits` and the applied `yields`. `GET /api/catalog` lists every archetype
  with its yield table, its habitability and its `water`.
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
  * `GET /api/galaxy/<name>/fleets` — the same across a whole galaxy, for the
    star map: it marks the stars where the player holds forces. Each fleet
    carries its `system_id`, so the client groups them; asking star by star
    would cost one request per system
  * `GET /api/system/<id>/army` — the same, summed per ship type
  * `POST /api/system/<id>/fleet` — create an empty fleet
  * `GET|POST|DELETE /api/fleet/<id>` — read, update (name, position, orbit),
    disband (empty fleets only)
  * `POST /api/fleet/<id>/position` — `{x, y, z}`, the hot path from Unity
  * `POST /api/fleet/<id>/orbit` — `{"territory_id": n}`, `null` or `0` detaches
  * `POST /api/fleet/<id>/transfer` — `{"to": n, "items": [{type, quantity}]}`
  * `POST /api/fleet/<id>/travel` — `{"system_id": n}`, sends the fleet along the
    star lanes; `DELETE` on the same path stops it at the last node it passed
  * `GET /api/galaxy/<name>/lanes` — the lane network itself, each lane once
    with its length. For clients that do not carry the neighbourhood rule
* `GET /api/territory/<id>/ships` **is gone**: ships are no longer a notion of
  the planet. Read them from the system, and recognise what holds a planet's
  orbit by each fleet's `orbiting_territory_id`.
* Migration: a database that already holds ships needs the migration run (see
  **Database schema and migrations**), which creates `fleet`, replaces
  `ship_territory` with `ship`, and pours each territory's stock into one fleet
  anchored in orbit of that territory. Migrated fleets start at the origin with
  no position: Unity gives them one the first time it shows the system.

## Travelling between stars
* A fleet crosses the galaxy **along the star lanes** — the same links the map
  draws between neighbouring stars — one hop at a time. That is what gives the
  map its relief: a system can be a choke point, a detour can cost dearly.
* The catch, and the reason `app/models/game/starlanes.py` exists: **those links
  were computed client-side**. `StarNeighbourhood` and the loop in
  `GalaxyFactory` derive them from star positions, and the server knew nothing
  of them. A server inventing its own links would fly fleets down routes the map
  does not show, so the rule is reproduced there **verbatim** — five nearest
  neighbours within six units, the radius widening by one until it finds two,
  capped by the galaxy's diagonal. **The constants are paired with Unity's
  (`Generator.LinkSearchRadius`, `LinksPerStar`, `MinLinksPerStar`): changing
  one side alone breaks the promise.**
* Routing is Dijkstra over those links, weighted by distance. Two clusters tight
  enough to satisfy themselves never link up, so `409` — no route — is a real
  answer, not a theoretical one.
* **Duration follows distance**: `TRAVEL_SECONDS_PER_UNIT`, 60 s per map unit
  before the galaxy's `fleet_speed_multiplier`. A typical six-unit hop is six
  minutes, the same order as a capital ship in the yard — deciding between
  building and moving only means something if both are paid in one currency.
* The route and each leg's duration are **frozen at departure**, stored on the
  fleet (`travel_route`, `travel_legs`, `travel_started_at`). A galaxy that grows
  mid-game must not reroute a fleet already under way, and the countdown the
  player is watching must not move under them.
* There is **no game loop**: a journey advances when it is read, like a
  territory's production. `Fleet.catch_up` runs before the fleet queries — and
  it has to run *before* the filter, since a fleet that has arrived still
  carries the id of the system it left, and would be listed in the wrong place.
* A fleet **belongs to the last node it passed**. Between two stars that is the
  one it just left: the server must be able to answer "which system?" at any
  moment, and a point in the void is not an answer. The client places it on the
  lane itself, from `travel.legs` and its own clock — no clock agreement needed
  between the two machines, since the server sends a remaining count and not an
  arrival time.
* **Departing leaves orbit.** Otherwise a shipyard left behind would keep
  delivering to a fleet halfway across the galaxy — it is `orbiting_territory_id`
  that decides, see `Fleet.receive_construction`.
* An order given **in flight does not turn around in the void**: the fleet
  finishes the hop it started and the new route begins at the node it reaches.
  It is also what stops a repeated order from standing still, every order
  otherwise restarting from the same point.
* In Unity, on the galaxy map: click a fleet's chevron, then **right-click a
  star** to send it there — the same gesture as the tactical view. Right-clicking
  the star it is currently at stops it.
* The web console does the same from its own galaxy map: pick a fleet, pick a
  star, confirm in the side panel. Its Fleets tab shows the route and the
  countdown but cannot start a journey — choosing a destination among three
  hundred stars is a map's job, and the tab has no map.
* Migration: `a4c7f2b81d63` adds the three travel columns. Fleets already in
  place are simply not travelling, which is what three null columns say.

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
* **The view lives in the path**, not in a query string — it is a page address,
  not a filter:
  * `/galaxy/<name>` — the map, which is the landing view
  * `/galaxy/<name>/territory/<id>` — one world
  * Bookmarkable, shareable, reloadable, and the browser's back button walks
    back through views instead of leaving the site. `/api` belongs to the API,
    so nothing collides
  * The server answers all of these with the same page (`app/web/ui.py`): a
    reload asks the server first, and without those routes a deep link would
    come back 404. Which galaxy to show is the client's business
  * `?galaxy=` links still work and are rewritten to the new form on the first
    navigation
  * The `<id>` is a **territory** id, not a system id: it is what makes the page
    deterministic, since a player can hold several worlds in one system
* Screens: resource bar, orbit rail for the system, and the Buildings /
  Shipyard / Fleets / Orbital Defences panel with live construction progress
* The Fleets tab is where ships are found once assembled: each fleet with its
  composition, the orbit it holds and the Unity position the server kept — plus
  renaming, anchoring to the current orbit, disbanding an empty fleet, and
  transferring ships between fleets of the system
* The **galaxy map** is the console's fourth screen, reached from the picker or
  from the top bar of a system. It answers what no list can: where things are
  relative to one another. Lists say what you hold; they never say whether two
  worlds are neighbours — and that is the only question that matters for moving
  a fleet, since a fleet only travels along the star lanes.
  * SVG, not canvas: stars are then elements, so hoverable, clickable and
    titled without writing a picking engine. They number in the hundreds, which
    the DOM carries easily
  * The lanes come from `GET /api/galaxy/<name>/lanes`. **The console has no
    copy of the neighbourhood rule** — it lives in `starlanes.py` and in the
    game client — and a map inventing its own links would show a network fleets
    do not use
  * Same scale on both axes, never a stretch to fill the frame: distance is
    what makes a hop's duration, and a stretched map would lie about both
  * Fleets advance on the local clock from `travel.legs`, exactly as the game
    client does; the server is re-read every fifteen seconds. It sends a
    remaining count, never an arrival time, so the two clocks need not agree
  * Pick a fleet, then a star, and the panel offers to send it there. This is
    what the console could not do before it had a map — and it is also where a
    `409` is read: two clusters tight enough to satisfy themselves never link up
  * Wheel to zoom, drag to pan, double-click one of your worlds to administer
    it, click empty space or press Escape to drop the selection. Panning writes
    the `viewBox` directly without repainting — a drag has to follow the mouse
    frame by frame; zooming repaints, since it is the one gesture that changes
    how large a star should be drawn
  * Zooming keeps the point under the cursor in place, and star radii, labels
    and fleet markers are divided by the zoom: zooming **separates** crowded
    stars rather than magnifying them, which is what one zooms a strategic map
    for. Below a threshold only your own worlds are named — three hundred
    overlapping labels read as nothing
* **Top bar**: the three everyday commands are icon buttons (galaxy map, my
  worlds, refresh); everything rare — galaxy settings, appearance, sign-out —
  sits under one menu on the right. The bar used to line up five buttons of
  equal weight, one of them red, for three daily gestures and three that are
  almost never made. Buttons are addressed by `data-act`, not by id: both scenes
  carry the same bar, and an id per button per scene meant two sets of wiring to
  keep in agreement
* Three visual directions ship together (Nebula Grid, Admiralty, Drydock); the
  switch lives in the settings dialog, off the top bar — appearance is set once
  and asks nothing again — and the choice is kept in `localStorage`
* Sources are plain HTML/CSS/ES modules under `app/static` — no build step:
  * `css/tokens.css` — one token set per direction
  * `css/components.css` — shared component library, reads only tokens
  * `js/api.js`, `js/app.js`, `js/icons.js`
* `POST /api/auth/logout` **now actually signs out.** It used to set
  `logged_in = False`, a flag nobody reads, and left Flask-Login's session
  untouched: the session cookie and the remember-me cookie — asked for at every
  login — survived, and the next request came back authenticated while the
  console showed the sign-in screen. Order matters in the fix: `logout_user()`
  signals the remember cookie deletion by writing `_remember = 'clear'` into the
  session, so clearing the session *after* it would carry that flag away with
  the rest and leave the cookie on the client

## API Documentation (Swagger UI)
* Open Swagger UI at `http://localhost:9000/api/docs`
* Open raw OpenAPI spec at `http://localhost:9000/api/openapi.json`

## Update OpenAPI Schema File
* Generate a schema file that matches the current Flask routes:
  * `python update_openapi_schema.py --routes-root app/web/api --app-web-root app/web --output app/web/api/openapi.generated.json`
