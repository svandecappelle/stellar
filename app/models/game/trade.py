# -*- coding: utf-8 -*-

"""
Les lignes de commerce : ce qui relie les mondes d'un empire.

Un cargo fait le premier voyage et **etablit la route** ; apres quoi les
ressources coulent d'elles-memes, sans qu'on pilote rien. On paie l'installation
une fois, et l'ennemi peut couper la ligne en tenant un bout.

Ce qu'une ligne exige
---------------------
Un **depot a chaque extremite**. Son niveau fixe le debit, et c'est le plus
faible des deux qui commande : monter le depot d'un cote seulement ne sert a
rien, ce qui donne au reseau une geometrie a entretenir plutot qu'un bouton a
presser.

Le depot n'est derriere aucune technologie. C'est deliberé : une ligne est la
seule reponse a l'isolement, et l'isolement coute de la stabilite des la
premiere heure — mettre le depot derriere l'arbre reviendrait a punir un joueur
pour une recherche qu'il n'a pas encore pu faire.

Ce qui circule
--------------
Les materiaux, les credits, le tritium et les **vivres**. Ces derniers sont le
coeur du systeme : c'est la faim qui tue, et une ligne est ce qui nourrit une
colonie qui ne produit pas assez. Ne circulent pas l'energie, qui se produit et
se consomme sur place sans stock, ni la population, qui voyage en vaisseau de
colonisation ou ne voyage pas.

Le reseau, et la capitale
-------------------------
Les lignes forment un graphe. Un territoire est **raccorde** s'il existe un
chemin de lignes actives jusqu'a la capitale de son proprietaire dans cette
galaxie ; deux territoires d'un meme systeme sont raccordes sans ligne. Tout le
reste s'etiole — voir la stabilite dans `territory.py`.

Mesurer l'isolement en chemin jusqu'a la capitale, et non en nombre de lignes,
n'est pas un detail : sous la seconde regle, deux mondes perdus relies l'un a
l'autre se declareraient tous deux raccordes.
"""

from datetime import datetime
import json

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.buildings import BuildingType


#: Debit d'un depot de niveau zero. Maigre, mais vivant : c'est ce qu'une
#: colonie recoit le jour de sa fondation, avant d'avoir rien construit.
THROUGHPUT_BASE = 40.0

#: Ce que chaque niveau de depot ajoute au debit, par heure.
THROUGHPUT_PER_LEVEL = 150.0


def throughput_of(territory):
    """Ce que le depot de ce territoire laisse passer, par heure."""
    if territory is None:
        return 0.0
    depot = territory.get_building(building_type=BuildingType.depot)
    return THROUGHPUT_BASE + THROUGHPUT_PER_LEVEL * float(depot.level or 0)


class TradeLine(Base):
    """
    Une route etablie entre deux territoires d'un meme joueur.

    Bidirectionnelle en tant qu'infrastructure : c'est la liste des flux qui dit
    ce qui va dans quel sens. Une ligne sans flux relie quand meme — elle suffit
    a rompre l'isolement, ce qui est deja sa moitie de l'interet.
    """

    __tablename__ = 'trade_line'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    origin_id = Column(Integer, ForeignKey("territory.id"), nullable=False)
    destination_id = Column(Integer, ForeignKey("territory.id"), nullable=False)

    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    #: Date de demontage. Une ligne fermee est GARDEE : elle dit au joueur
    #: qu'une route a existe, et a quel moment elle a cesse.
    closed_at = Column(DateTime, nullable=True)

    #: Les flux declares, en JSON : [{"resource": "food", "to_origin": false,
    #: "rate": 280.0}]. Une colonne JSON plutot qu'une table : un flux n'a pas
    #: d'existence hors de sa ligne, et en ajouter un ne doit pas demander de
    #: migration.
    _flows = Column("flows", String, nullable=True)

    user = relationship("User")
    origin = relationship("Territory", foreign_keys=[origin_id])
    destination = relationship("Territory", foreign_keys=[destination_id])

    __table_args__ = (
        Index('ix_trade_line_user_id', 'user_id'),
        Index('ix_trade_line_origin_id', 'origin_id'),
        Index('ix_trade_line_destination_id', 'destination_id'),
    )

    def __init__(self, user_id, origin_id, destination_id, flows=None):
        self.user_id = user_id
        self.origin_id = origin_id
        self.destination_id = destination_id
        self.flows = flows or []

    def __repr__(self):
        return '<TradeLine {} {}->{}>'.format(
            self.id, self.origin_id, self.destination_id)

    # ── Les flux ────────────────────────────────────────────────────────────

    @property
    def flows(self):
        if not self._flows:
            return []
        try:
            return json.loads(self._flows)
        except (TypeError, ValueError):
            # Une ligne au contenu illisible relie encore : on perd ses flux,
            # pas la route. Couper le raccordement pour cela ferait s'etioler
            # un monde a cause d'une ligne de JSON.
            return []

    @flows.setter
    def flows(self, value):
        self._flows = json.dumps(value or [])

    @property
    def is_open(self):
        return self.closed_at is None

    def close(self, now=None):
        if self.closed_at is None:
            self.closed_at = now or datetime.utcnow()
        return self

    # ── Le debit ────────────────────────────────────────────────────────────

    @property
    def throughput(self):
        """
        Ce que la ligne laisse passer par heure, tous flux confondus.
        ---
        Le plus faible des deux depots : monter celui du depart seulement ne
        change rien, et c'est ce qui fait du reseau une geometrie plutot qu'un
        bouton.
        """
        return min(throughput_of(self.origin), throughput_of(self.destination))

    # ── Lecture ─────────────────────────────────────────────────────────────

    @classmethod
    def of(cls, user, open_only=True):
        """Les lignes de ce joueur."""
        query = db.session.query(cls).filter(cls.user_id == user.id)
        if open_only:
            query = query.filter(cls.closed_at.is_(None))
        return query.order_by(cls.id).all()

    @classmethod
    def between(cls, origin, destination, open_only=True):
        """
        La ligne qui relie ces deux territoires, dans un sens ou dans l'autre.
        ---
        Une route n'a pas de sens : la rechercher dans les deux ordres evite
        d'en ouvrir une seconde a rebours de la premiere.
        """
        query = db.session.query(cls).filter(
            ((cls.origin_id == origin.id) & (cls.destination_id == destination.id))
            | ((cls.origin_id == destination.id) & (cls.destination_id == origin.id))
        )
        if open_only:
            query = query.filter(cls.closed_at.is_(None))
        return query.first()

    @classmethod
    def touching(cls, territory, open_only=True):
        """Les lignes dont ce territoire est une extremite."""
        query = db.session.query(cls).filter(
            (cls.origin_id == territory.id) | (cls.destination_id == territory.id))
        if open_only:
            query = query.filter(cls.closed_at.is_(None))
        return query.order_by(cls.id).all()

    def other_end(self, territory):
        """L'autre bout, `None` si ce territoire n'est pas une extremite."""
        if territory is None:
            return None
        if territory.id == self.origin_id:
            return self.destination
        if territory.id == self.destination_id:
            return self.origin
        return None

    # ── Publication ─────────────────────────────────────────────────────────

    @property
    def serialize(self):
        return {
            'id': self.id,
            'origin_id': self.origin_id,
            'destination_id': self.destination_id,
            'origin': self.origin.name if self.origin else None,
            'destination': self.destination.name if self.destination else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'open': self.is_open,
            'throughput': self.throughput,
            'flows': self.flows,
            # Ce que le joueur doit voir sans avoir a le deduire : une ligne
            # bloquee reste ouverte, elle ne coule simplement plus.
            'blockaded': self.is_blockaded,
        }

    # ── Le blocus ───────────────────────────────────────────────────────────

    @property
    def is_blockaded(self):
        """
        Une flotte hostile tient-elle un bout de cette ligne ?

        Rien n'est detruit : le blocus est un robinet, pas une demolition. La
        ligne reste ouverte et redevient coulante des que la flotte s'en va.

        **Ne verifie que les deux extremites**, pas les systemes traverses. Le
        chemin existe — `app/models/game/starlanes.py` sait le calculer — mais
        le parcourir a chaque tour de chaque monde couterait plus que ce qu'il
        rapporte tant qu'aucun combat ne se joue en route. C'est une limite
        assumee, pas un oubli.
        """
        from app.models.game.fleet import Fleet

        for end in (self.origin, self.destination):
            if end is None:
                continue
            hostile = (
                db.session.query(Fleet)
                .filter(Fleet.system_id == end.system_id)
                .filter(Fleet.user_id != self.user_id)
                .first()
            )
            if hostile is not None:
                return True
        return False
