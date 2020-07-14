from datetime import datetime, timedelta
import enum

from app.application import db
from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship


class UserEventType(enum.Enum):
    message = "message"


class PositionalEventType(enum.Enum):
    technology = "technology"
    building = "building"


class Event:

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    finishing_at = Column(DateTime, nullable=False)


class UserEvent(Base, Event):
    __tablename__ = 'user_event'

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(Enum(UserEventType), nullable=False)
    extra_args = Column(String, nullable=False)

    def __init__(self, user_id, finishing_at, event_type, extra_args):
        self.user_id = user_id
        self.finishing_at = finishing_at
        self.event_type = event_type
        self.extra_args = extra_args

    @classmethod
    def create(cls, user, duration, event_type, extra_args):
        """
        Create an event
        ---
        :return:
        """
        event = UserEvent(
            user_id=user.id,
            finishing_at=datetime.utcnow() + timedelta(seconds=duration),
            event_type=event_type,
            extra_args=str(extra_args)
        )
        db.session.flush()
        db.session.add(event)
        return event

    @classmethod
    def all(cls, user, event_type):
        """
        Fetch all
        ---
        :param user:
        :param event_type:
        :return:
        """
        query = db.session.query(UserEvent)\
            .filter(cls.user_id == user.id)
        if event_type:
            query = query.filter(cls.event_type == event_type)
        return query.all()

    @property
    def serialize(self):
        return {
            'id': self.id,
            'eventType': str(self.event_type),
            'extraArgs': self.extra_args,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
            'finishingAt': self.finishing_at
        }


class PositionalEvent(Base, Event):
    __tablename__ = 'positional_event'

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(Enum(PositionalEventType), nullable=False)
    extra_args = Column(String, nullable=False)

    on_territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)
    on_territory = relationship("PositionalEventDetail", uselist=False, back_populates="event")

    def __init__(self, territory, user_id, finishing_at, event_type, extra_args):
        self.user_id = user_id
        self.finishing_at = finishing_at
        self.event_type = event_type
        self.extra_args = extra_args
        self.on_territory_id = territory.system.id

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def create(cls, territory, user, duration, event_type, extra_args):
        """
        Create an event
        ---
        :return:
        """
        event = PositionalEvent(
            territory=territory,
            user_id=user.id,
            finishing_at=datetime.utcnow() + timedelta(seconds=duration),
            event_type=event_type,
            extra_args=str(extra_args)
        )
        db.session.add(event)
        db.session.flush()

        detail = PositionalEventDetail(
            event_id=event.id,
            territory_id=territory.id,
            extra_data=str(extra_args)
        )
        db.session.add(detail)

        return event

    @classmethod
    def all(cls, user, event_type):
        """
        Fetch all
        ---
        :param user:
        :param event_type:
        :return:
        """
        query = db.session.query(PositionalEvent) \
            .filter(cls.user_id == user.id)
        if event_type:
            query = query.filter(cls.event_type == event_type)
        return query.all()

    @property
    def serialize(self):
        return {
            'id': self.id,
            'eventType': str(self.event_type),
            'extraArgs': self.extra_args,
            'onTerritory': self.on_territory.serialize,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
            'finishingAt': self.finishing_at,
        }


class PositionalEventDetail(Base):
    __tablename__ = 'event_detail'

    event_id = Column(Integer, ForeignKey('positional_event.id'), primary_key=True)
    territory_id = Column(Integer, ForeignKey('territory.id'), primary_key=True)
    extra_data = Column(String(2500))

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territory = relationship("Territory", back_populates="territory_events")
    event = relationship("PositionalEvent", back_populates="on_territory")

    def __init__(self, event_id, territory_id, extra_data):
        self.event_id = event_id
        self.territory_id = territory_id
        self.extra_data = extra_data

    @property
    def serialize(self):
        return {
            'eventId': self.event_id,
            'territory': self.territory.serialize,
            'extraData': self.extra_data,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at
        }
