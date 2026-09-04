# -*- coding: utf-8 -*-

"""
Web UI: serves the single page console and the static catalogue it needs.

The console is plain HTML/CSS/ES modules under `app/static`, served from the
same origin as the API so that the Flask-Login session cookie applies.
"""

import os

from flask import jsonify, send_from_directory

from app.application import app, login_required
from app.models.game.buildings import BuildingType
from app.models.game.defense import DefenseType
from app.models.game.planet import PlanetArchetype, scheme_map
from app.models.game.ship import ShipType
from app.models.game.technologies.technology_type import TechnologyType
from app.models.game.territory import ResourceType

STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


@app.route('/', methods=['GET'])
def ui_index():
    """Serve the console entry point."""
    return send_from_directory(STATIC_ROOT, 'index.html')


def _unit_entry(unit):
    """
    Describe a ship or defense type.
    ---
    The enum member name is authoritative: it is what `Territory.build` accepts
    and what `Ship.serialize` returns. The nested `name` value is not always
    consistent with it.
    """
    return {
        'name': unit.name,
        'cost': unit.value.get('base_cost', {}),
        'integrity': unit.value.get('integrity', 0),
        'requirements': unit.value.get('requirements', {}),
    }


@app.route('/api/catalog', methods=['GET'])
@login_required
def get_catalog():
    """
    Static game catalogue: everything the UI needs to offer a build that the
    territory payload does not already carry (ship and defense costs).
    """
    return jsonify({
        'resources': [r.name for r in ResourceType],
        'materials': [r.name for r in ResourceType.materials()],
        'archetypes': PlanetArchetype.serialize_all(),
        # Table planeteScheme -> archetype : le lien entre l'apparence tiree par
        # le client et ce que la planete produit.
        'planet_schemes': scheme_map(),
        'buildings': [b.name for b in BuildingType],
        'ships': [_unit_entry(s) for s in ShipType],
        'defenses': [_unit_entry(d) for d in DefenseType],
        'technologies': [
            {'name': t.name, 'cost': t.value.get('base_cost', {})}
            for t in TechnologyType
        ],
    })
