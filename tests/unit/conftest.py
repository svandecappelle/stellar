# -*- coding: utf-8 -*-

"""
Le socle des tests unitaires.

Ce qui les separe des tests d'API voisins : ni base, ni application, ni requete.
Les modeles sont instancies a la main et on lit ce qu'ils calculent. C'est la
que vivent les regles du jeu -- ce qu'un extracteur remonte, ce qu'une famine
coute, quelles etoiles se relient -- et c'est la qu'une formule fausse se voit,
sans avoir a jouer un tour entier pour l'atteindre.

Deux consequences, dont tout ce dossier decoule :

  · `tests/conftest.py` monte une base et une application pour chaque test, par
    `autouse`. On redefinit ici une fixture vide du meme nom -- pytest retient la
    plus proche -- et rien ne se construit avant ces tests-ci ;
  · les valeurs par defaut des colonnes sont posees par la base au moment de
    l'ecriture. Un modele jamais ecrit a donc ses colonnes a None, y compris
    `food` ou `stability`. Les fabriques ci-dessous les appliquent depuis la
    declaration des colonnes plutot que de les recopier : recopier ferait mentir
    les tests le jour ou une valeur de depart change.
"""

import pytest

from app.models.game import starlanes
from app.models.game.buildings import Building, BuildingType
from app.models.game.defense import Defense, DefenseType
from app.models.game.planet import PlanetArchetype
from app.models.game.settings import GalaxySettings
from app.models.game.system import System
from app.models.game.territory import Territory
from app.models.user import User


@pytest.fixture(autouse=True, scope='function')
def flask_app():
    """
    Neutralise la fixture du meme nom, qui batit une base a chaque test.
    ---
    Voir l'en-tete : un test unitaire n'a pas de base a construire, et les
    quelques secondes gagnees a chaque appel sont ce qui fait qu'on les lance.
    """
    yield None


def apply_column_defaults(instance):
    """
    Pose sur un modele les valeurs que la base lui donnerait a l'ecriture.
    ---
    Lues depuis la declaration des colonnes : un territoire neuf part avec les
    memes reserves ici qu'en jeu, et le jour ou l'une d'elles change, ces tests
    suivent sans etre touches. Les defauts calcules -- les horodatages -- sont
    laisses de cote : ils n'ont rien a dire aux regles du jeu.
    """
    for column in instance.__table__.columns:
        default = column.default
        if default is None or default.is_callable:
            continue
        setattr(instance, column.name, default.arg)
    return instance


class Stub(object):
    """
    Un objet reduit aux attributs qu'on lui passe.

    De quoi tenir lieu de modele la ou le code n'en lit qu'un attribut ou deux :
    un systeme dont le graphe des liaisons ne veut que la position, par exemple.
    """

    def __init__(self, **attributes):
        self.__dict__.update(attributes)


@pytest.fixture(name="stub")
def stub():
    """`Stub`, pour les tests qui en fabriquent eux-memes."""
    return Stub


@pytest.fixture(autouse=True)
def forget_lane_graphs():
    """
    Le graphe des liaisons est garde dans une globale de module.
    ---
    Il se controle tout seul en jeu, en comparant les positions qui l'ont
    produit. Entre deux tests, ces positions sont fabriquees : deux galaxies
    portant le meme nom se succederaient, et la seconde lirait le graphe de la
    premiere.
    """
    starlanes.forget()
    yield
    starlanes.forget()


@pytest.fixture(name="place")
def place(monkeypatch, stub):
    """
    Pose une galaxie d'etoiles fictives et rend leurs systemes.
    ---
    Le graphe des liaisons ne lit d'un systeme que son identifiant et sa
    position : il n'y a donc rien a mettre en base pour l'eprouver, ni pour
    faire voyager une flotte dessus. Les identifiants vont de 1 a n dans
    l'ordre donne, ce qui rend les attentes lisibles.
    """
    def build(positions):
        systems = [stub(id=index + 1, position=position)
                   for index, position in enumerate(positions)]
        monkeypatch.setattr(
            System, 'all_of', classmethod(lambda cls, galaxy_name: systems))
        starlanes.forget()
        return systems
    return build


@pytest.fixture(name="tune")
def tune(monkeypatch):
    """
    Pose des reglages sur la galaxie, sans ligne en base.
    ---
    `GalaxySettings.row_for` est le seul point de contact avec la base ; on le
    remplace par la ligne voulue. Les modeles de jeu lisent leurs reglages par
    `GalaxySettings.value`, quel que soit le nom de galaxie -- ici None, un
    territoire hors systeme n'en ayant pas -- et c'est justement ce chemin-la
    qu'on vient eprouver.
    """
    def apply(**values):
        row = GalaxySettings(galaxy_name="test", overrides=values)
        monkeypatch.setattr(
            GalaxySettings, 'row_for', classmethod(lambda cls, galaxy_name: row))
        return row
    return apply


@pytest.fixture(name="make_territory")
def make_territory():
    """
    Un territoire complet, en memoire, sans une ligne en base.
    ---
    Complet veut dire : ses batiments au niveau zero et ses batteries, comme
    `Territory.create` les pose, un archetype et des gisements decides plutot
    que tires au sort, et un proprietaire -- la production passe par sa faction,
    un monde sans habitant ne sait pas se calculer.
    """
    def build(archetype=PlanetArchetype.telluric, deposits=None, user=None, **columns):
        territory = Territory(
            system=Stub(id=1),
            position_in_system=1,
            archetype=archetype,
        )
        apply_column_defaults(territory)
        territory.id = 1
        # Tires au hasard par le constructeur : on les fixe, sans quoi le
        # rendement d'un extracteur varierait d'une execution a l'autre.
        territory.deposits = deposits if deposits is not None else {
            material: 1.0 for material in archetype.materials}

        territory.user = user if user is not None else User(
            username="pilote", email="pilote@testing.com")
        territory.user_id = 1

        for building_type in BuildingType:
            territory.buildings.append(
                Building(territory_id=territory.id, type=building_type))
        for defense_type in DefenseType:
            territory.defenses.append(
                Defense(territory_id=territory.id, type=defense_type))

        for name, value in columns.items():
            setattr(territory, name, value)
        return territory
    return build
