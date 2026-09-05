# -*- coding: utf-8 -*-

"""
Reglages de jeu d'une galaxie.

Une galaxie est une partie : deux parties sur le meme serveur n'ont pas a
tourner au meme rythme. Ces reglages sont les boutons qui changent ce rythme —
diviser les temps de construction, multiplier l'extraction — sans toucher aux
tables de valeurs, qui restent les memes pour tout le monde.

Trois regles ont guide le choix des parametres :

  · chacun s'applique en UN seul endroit, celui que lisent a la fois l'API, la
    console et le client de jeu. Un facteur applique a la production mais pas a
    la valeur affichee ferait mentir l'interface ;
  · chacun porte sur ce qu'une galaxie possede. Les technologies appartiennent
    au joueur, toutes galaxies confondues : un multiplicateur de recherche par
    galaxie n'aurait pas de sens et n'est donc pas propose ;
  · la valeur 1.0 ne change rien. Une galaxie sans reglage joue exactement comme
    avant, et la table peut rester vide.

Les valeurs sont stockees dans une colonne JSON plutot que dans des colonnes
nommees : ajouter un parametre est alors une modification de code, sans
migration de schema.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, JSON, VARCHAR

from app.application import db
from app.models.base import Base


class Parameter(object):
    """
    Un reglage : ce qu'il vaut par defaut, ce qu'il change, et ses bornes.

    Le libelle et l'explication vivent ici et non dans la console : c'est le
    serveur qui applique le reglage, c'est a lui de dire ce qu'il fait. La
    console construit son formulaire a partir de cette description.
    """

    def __init__(self, key, label, description, default, minimum, maximum, step=0.1):
        self.key = key
        self.label = label
        self.description = description
        self.default = default
        self.minimum = minimum
        self.maximum = maximum
        self.step = step

    def clean(self, raw):
        """
        Valeur utilisable, ou ValueError disant pourquoi.

        Les bornes sont refusees et non ramenees : un moderateur qui tape 1000
        s'est trompe de champ, et lui rendre 100 sans rien dire lui laisserait
        croire que sa valeur est passee.
        """
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError("%s: %r n'est pas un nombre" % (self.key, raw))

        if value != value or value in (float('inf'), float('-inf')):
            raise ValueError("%s: valeur hors du domaine reel" % self.key)

        if value < self.minimum or value > self.maximum:
            raise ValueError(
                "%s: %g est hors des bornes [%g, %g]"
                % (self.key, value, self.minimum, self.maximum)
            )

        return value

    @property
    def serialize(self):
        return {
            'key': self.key,
            'label': self.label,
            'description': self.description,
            'default': self.default,
            'min': self.minimum,
            'max': self.maximum,
            'step': self.step,
        }


#: Les reglages, dans l'ordre ou la console les presente.
PARAMETERS = [
    Parameter(
        key='build_time_divider',
        label='Acceleration des constructions',
        description=(
            "Divise la duree de toutes les constructions du territoire : "
            "batiments, vaisseaux et defenses. 2 construit deux fois plus vite, "
            "0.5 deux fois plus lentement."
        ),
        default=1.0,
        minimum=0.05,
        maximum=1000.0,
    ),
    Parameter(
        key='extraction_multiplier',
        label='Rendement des extracteurs',
        description=(
            "Multiplie ce que l'extracteur remonte du sol. N'agit que sur les "
            "materiaux extraits : ce que produisent la centrale, la raffinerie "
            "ou le centre economique n'en depend pas."
        ),
        default=1.0,
        minimum=0.05,
        maximum=1000.0,
    ),
    Parameter(
        key='resource_gain_multiplier',
        label='Production generale',
        description=(
            "Multiplie toute production horaire, extraction comprise. C'est le "
            "reglage a bouger pour accelerer une partie entiere ; le rendement "
            "des extracteurs s'y ajoute, les deux se multipliant."
        ),
        default=1.0,
        minimum=0.05,
        maximum=1000.0,
    ),
    Parameter(
        key='building_cost_multiplier',
        label='Cout des batiments',
        description=(
            "Multiplie le cout du niveau suivant de chaque batiment. En dessous "
            "de 1 les paliers tombent plus vite, au-dessus la partie se durcit."
        ),
        default=1.0,
        minimum=0.05,
        maximum=100.0,
    ),
    Parameter(
        key='starting_resources_multiplier',
        label='Stock de depart',
        description=(
            "Multiplie les ressources trouvees sur un monde au moment ou un "
            "joueur s'y installe. Sans effet sur les mondes deja colonises."
        ),
        default=1.0,
        minimum=0.1,
        maximum=1000.0,
    ),
]

PARAMETERS_BY_KEY = {parameter.key: parameter for parameter in PARAMETERS}

DEFAULTS = {parameter.key: parameter.default for parameter in PARAMETERS}


class GalaxySettings(Base):
    """
    Les reglages poses sur une galaxie, s'il y en a.

    Une ligne n'existe que si quelqu'un a change quelque chose, et elle ne
    retient que les valeurs qui different du defaut : une galaxie sans ligne et
    une galaxie remise a zero se jouent de la meme facon.
    """

    __tablename__ = 'galaxy_settings'

    galaxy_name = Column(VARCHAR(255), ForeignKey("galaxy.name"), primary_key=True)

    #: Uniquement ce qui a ete change. Voir `effective_for`.
    overrides = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, galaxy_name, overrides=None):
        self.galaxy_name = galaxy_name
        self.overrides = overrides or {}

    def __repr__(self):
        return '<galaxy_settings {}>'.format(self.galaxy_name)

    @classmethod
    def row_for(cls, galaxy_name):
        """
        La ligne de cette galaxie, ou None.

        Passe par `Query.get`, qui repond depuis l'identity map de la session :
        les reglages sont lus une fois par batiment serialise, et une requete a
        chaque fois se verrait.
        """
        if not galaxy_name:
            return None
        return db.session.query(cls).get(galaxy_name)

    @classmethod
    def effective_for(cls, galaxy_name):
        """Tous les reglages de la galaxie, defauts compris."""
        values = dict(DEFAULTS)
        row = cls.row_for(galaxy_name)
        if row and row.overrides:
            for key, value in row.overrides.items():
                if key in PARAMETERS_BY_KEY:
                    values[key] = value
        return values

    @classmethod
    def value(cls, galaxy_name, key):
        """
        Un reglage, avec son defaut en secours.

        C'est l'appel que font les modeles de jeu : il ne leve jamais, une
        galaxie inconnue ou une base sans table rendant simplement le defaut.
        Un reglage n'est pas une regle du jeu, il ne doit pas pouvoir casser une
        partie.
        """
        default = DEFAULTS.get(key, 1.0)
        try:
            row = cls.row_for(galaxy_name)
        except Exception:  # noqa: BLE001 - table absente : on joue sans reglages
            # Une requete en echec laisse la transaction cassee sous Postgres :
            # tout ce qui suivrait echouerait aussi. On la rend au propre avant
            # de repartir sur le defaut.
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            return default

        if not row or not row.overrides:
            return default

        raw = row.overrides.get(key, default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @classmethod
    def write(cls, galaxy_name, wanted):
        """
        Ecrit les reglages donnes et rend l'etat effectif.

        Les cles absentes ne sont pas touchees : la console envoie le formulaire
        entier, mais un appel d'API peut n'en changer qu'une. Une valeur egale
        au defaut est retiree plutot qu'enregistree, pour que la ligne dise
        exactement ce qui a ete modifie.
        """
        if not isinstance(wanted, dict):
            raise ValueError("Les reglages doivent etre un objet cle/valeur")

        unknown = [key for key in wanted if key not in PARAMETERS_BY_KEY]
        if unknown:
            raise ValueError("Reglage inconnu : %s" % ", ".join(sorted(unknown)))

        cleaned = {
            key: PARAMETERS_BY_KEY[key].clean(raw)
            for key, raw in wanted.items()
        }

        row = cls.row_for(galaxy_name)
        if row is None:
            row = cls(galaxy_name=galaxy_name)
            db.session.add(row)

        # Reaffecte plutot que de modifier en place : une colonne JSON modifiee
        # dans son dictionnaire ne se declare pas sale, et rien ne partirait en
        # base.
        overrides = dict(row.overrides or {})
        for key, value in cleaned.items():
            if value == PARAMETERS_BY_KEY[key].default:
                overrides.pop(key, None)
            else:
                overrides[key] = value

        row.overrides = overrides
        db.session.commit()

        return cls.effective_for(galaxy_name)

    @property
    def serialize(self):
        return {
            'galaxy_name': self.galaxy_name,
            'settings': self.effective_for(self.galaxy_name),
            'overrides': dict(self.overrides or {}),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
