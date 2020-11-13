from datetime import datetime
import enum

from app.application import db
from app.models.base import Base

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, VARCHAR
from sqlalchemy.orm import relationship


class FactionAdvantageType(enum.Enum):
    Cost = "cost"
    Power = "power"
    Production = "production"
    Resistance = "resistance"
    TimeReduce = "time_reduce"


class FactionAdvantageScope(enum.Enum):
    Resource = "resources"
    Ships = "ships"
    Buildings = "buildings"
    Defenses = "defenses"
    Technologies = "technologies"


class FactionAdvantages(Base):
    """
    """

    __tablename__ = 'faction_advantages'

    id = Column(Integer, primary_key=True)
    faction_id = Column(Integer, ForeignKey("factions.id"), nullable=False)
    advantage_type = Column(Enum(FactionAdvantageType), nullable=False)
    advantage_scope = Column(Enum(FactionAdvantageScope), nullable=False)
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
                'scope': ResourceType.mater.name,
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

    def apply(self, obj, advantage_scope, scope=None):
        """
        """
        advantages = [a for a in self.advantages if a.advantage_scope == advantage_scope]
        for a in advantages:
            if a.advantage_scope_args.get('scope', True) is True or a.advantage_scope_args['scope'] == scope:
                if a.advantage_scope_args['percentage']:
                    obj += obj * a.advantage_scope_args['percentage'] / 100
        return obj

    @property
    def serialize(self):
        return {
            "id": self.id,
            "name": self.name
        }
