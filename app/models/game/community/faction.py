from datetime import datetime

from app.application import db
from app.models.base import Base
from app.models.game.modifiers import Modifier, ModifierScope, ModifierSet, ModifierType

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, VARCHAR
from sqlalchemy.orm import relationship


#: Une faction n'a plus son vocabulaire a elle : ce qu'elle pose sont des
#: modificateurs, comme ceux que rend l'arbre technologique, et les deux
#: s'empilent dans le meme `ModifierSet`. Les deux noms restent parce qu'ils
#: sont lus partout dans le jeu et dans les tests ; ils ne designent plus qu'un
#: alias.
#:
#: Les membres des cinq premiers cas portent les memes noms qu'avant, et c'est
#: le nom que SQLAlchemy ecrit en base : les lignes deja enregistrees restent
#: lisibles. Le type Postgres, lui, garde son nom d'origine grace au `name=`
#: pose sur les colonnes ci-dessous — sans quoi SQLAlchemy en deduirait
#: `modifiertype` et ne retrouverait plus le type existant.
FactionAdvantageType = ModifierType
FactionAdvantageScope = ModifierScope


class FactionAdvantages(Base):
    """
    """

    __tablename__ = 'faction_advantages'

    id = Column(Integer, primary_key=True)
    faction_id = Column(Integer, ForeignKey("factions.id"), nullable=False)
    advantage_type = Column(
        Enum(ModifierType, name='factionadvantagetype'), nullable=False)
    advantage_scope = Column(
        Enum(ModifierScope, name='factionadvantagescope'), nullable=False)
    advantage_scope_args = Column(JSON, nullable=False)

    def __init__(self, faction_id, advantage_type, advantage_scope, advantage_scope_args):
        self.faction_id = faction_id
        self.advantage_type = advantage_type
        self.advantage_scope = advantage_scope
        self.advantage_scope_args = advantage_scope_args


class Faction(Base):
    """
    Faction is a user group that affect users by adding some advantages
    """

    __tablename__ = 'factions'

    id = Column(Integer, primary_key=True)
    name = Column(VARCHAR(250), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    advantages = relationship("FactionAdvantages")

    def __init__(self, name):
        self.name = name

    @classmethod
    def initialize(cls, session):
        from app.models.game.territory import ResourceType

        technocrats = Faction(
            name="Technocrats"
        )
        warriors = Faction(
            name="Warriors"
        )
        merchants = Faction(
            name="Merchants"
        )

        session.add(technocrats)
        session.add(warriors)
        session.add(merchants)
        session.flush()

        technocrats.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.TimeReduce,
            advantage_scope=FactionAdvantageScope.Technologies,
            advantage_scope_args={
                'percentage': -10
            }
        ),
        technocrats.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.Production,
            advantage_scope=FactionAdvantageScope.Resource,
            advantage_scope_args={
                'percentage': 1,
                # Technocrats lean on the material their research runs on.
                'scope': ResourceType.silicium.name,
            }
        )

        warriors.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.Power,
            advantage_scope=FactionAdvantageScope.Ships,
            advantage_scope_args={
                'percentage': 10
            }
        )
        warriors.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.Production,
            advantage_scope=FactionAdvantageScope.Resource,
            advantage_scope_args={
                'percentage': 1,
                'scope': ResourceType.tritium.name,
            }
        )

        merchants.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.Production,
            advantage_scope=FactionAdvantageScope.Buildings,
            advantage_scope_args={
                'percentage': 3
            }
        )
        merchants.add_advantage(
            session=session,
            advantage_type=FactionAdvantageType.Production,
            advantage_scope=FactionAdvantageScope.Resource,
            advantage_scope_args={
                'percentage': 1,
                'scope': ResourceType.credits.name,
            }
        )


    @classmethod
    def all(cls, session):
        return session.query(cls).all()

    @classmethod
    def get(cls, id):
        """
        ---
        """
        return db.session.query(cls).filter(cls.id == id).one()

    def add_user(self, user):
        """
        Affect a user to the faction
        ---
        :param user:
        :return:
        """

    def add_advantage(self, session, advantage_type, advantage_scope, advantage_scope_args):
        advantage = FactionAdvantages(
            faction_id=self.id,
            advantage_type=advantage_type,
            advantage_scope=advantage_scope,
            advantage_scope_args=advantage_scope_args
        )
        session.add(advantage)
        session.flush()

    @property
    def modifiers(self):
        """
        Ce que la faction apporte, dit dans le vocabulaire commun.
        ---
        Chaque ligne d'avantage devient un `Modifier`. La cle `scope` des
        arguments — heritee, et qui designait en fait une cible et non une
        portee — se lit ici comme la cible : c'est ce qu'elle a toujours voulu
        dire (`{'scope': 'silicium'}` sur une portee Resource).
        """
        modifiers = []
        for advantage in self.advantages:
            args = advantage.advantage_scope_args or {}
            target = args.get('scope')
            modifiers.append(Modifier(
                type=advantage.advantage_type,
                scope=advantage.advantage_scope,
                percentage=args.get('percentage', 0),
                flat=args.get('flat', 0),
                target=None if target in (None, True) else target,
                source="faction:%s" % self.name,
            ))
        return modifiers

    def apply(self, obj, advantage_scope, scope=None):
        """
        Appliquer les avantages de la faction a une valeur.
        ---
        Conserve pour les appelants qui ne connaissent que la faction. Le calcul
        vit desormais dans `ModifierSet` : les pourcentages d'une meme portee
        s'y additionnent au lieu de se composer, ce qui ne change rien tant
        qu'une faction n'a qu'un avantage par portee — c'est le cas des trois
        factions livrees — et rend l'affichage fidele au calcul des qu'elle en
        aura deux.

        Prefer `user.modifiers` a ce raccourci : lui seul empile aussi la
        recherche.
        """
        return ModifierSet(self.modifiers).apply(
            value=obj, scope=advantage_scope, target=scope)

    @property
    def serialize(self):
        return {
            "id": self.id,
            "name": self.name
        }
