from datetime import datetime, timedelta
import enum
import json

from app.application import db
from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, and_
from sqlalchemy.orm import relationship, synonym


class UserEventType(enum.Enum):
    message = "message"


class PositionalEventType(enum.Enum):
    technology = "technology"
    building = "building"
    defense = "defense"


class Event:

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    finishing_at = Column(DateTime, nullable=False)


class UserEvent(Base, Event):
    __tablename__ = 'user_event'

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(Enum(UserEventType), nullable=False)
    _extra_args = Column(String, nullable=True)
    archived_at = Column(DateTime, nullable=True)

    user = relationship("User", uselist=False)

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
            extra_args=extra_args
        )
        db.session.flush()
        db.session.add(event)
        return event

    @classmethod
    def all(cls, user, event_type=None, include_archived=False):
        """
        Fetch all
        ---
        :param include_archived:
        :param user:
        :param event_type:
        :return:
        """
        query = db.session.query(UserEvent)\
            .filter(cls.user_id == user.id)
        if event_type:
            query = query.filter(cls.event_type == event_type)
        if not include_archived:
            query = query.filter(cls.archived_at == None)
        return query.all()

    @property
    def extra_args(self):
        return json.loads(self._extra_args)

    @extra_args.setter
    def extra_args(self, v):
        if isinstance(v, dict):
            self._extra_args = json.dumps(v)
            return
        if isinstance(v, str):
            self._extra_args = v
            return
        raise TypeError("Expected str or dict for event args, got {}".format(type(v)))

    extra_args = synonym("_extra_args", descriptor=extra_args)

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


# TODO add a positional event with two users (from, to)
class PositionalEvent(Base, Event):
    __tablename__ = 'positional_event'

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(Enum(PositionalEventType), nullable=False)
    _extra_args = Column(String, nullable=False)
    archived_at = Column(DateTime, nullable=True)

    on_territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)
    details = relationship("PositionalEventDetail", uselist=False, back_populates="event")

    user = relationship("User", uselist=False)

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
            extra_args=extra_args
        )
        db.session.add(event)
        db.session.flush()

        detail = PositionalEventDetail(
            event_id=event.id,
            territory_id=territory.id,
            extra_data=extra_args
        )
        db.session.add(detail)

        return event

    def update_event(self):
        """
        Update event from its origin territory
        ---
        :return:
        """
        self.details.update_event()

    def archive(self):
        self.archived_at = datetime.utcnow()

    @classmethod
    def all(cls, user, event_type=None, include_archived=False):
        """
        Fetch all
        ---
        :param include_archived:
        :param user:
        :param event_type:
        :return:
        """
        query = db.session.query(PositionalEvent) \
            .filter(cls.user_id == user.id)
        if event_type:
            query = query.filter(cls.event_type == event_type)
        if not include_archived:
            query = query.filter(cls.archived_at == None)
        return query.all()

    @property
    def extra_args(self):
        return json.loads(self._extra_args)

    @extra_args.setter
    def extra_args(self, v):
        if isinstance(v, dict):
            self._extra_args = json.dumps(v)
            return
        if isinstance(v, str):
            self._extra_args = v
            return
        raise TypeError("Expected str or dict for event args, got {}".format(type(v)))

    extra_args = synonym("_extra_args", descriptor=extra_args)

    @property
    def serialize(self):
        return {
            'id': self.id,
            'eventType': str(self.event_type),
            'extraArgs': self.extra_args,
            'details': self.details.serialize,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
            'finishingAt': self.finishing_at,
        }


class PositionalEventDetail(Base):
    __tablename__ = 'event_detail'

    event_id = Column(Integer, ForeignKey('positional_event.id'), primary_key=True)
    territory_id = Column(Integer, ForeignKey('territory.id'), primary_key=True)
    _extra_data = Column(String(2500))

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territory = relationship("Territory", back_populates="territory_events")
    event = relationship("PositionalEvent", back_populates="details")

    def __init__(self, event_id, territory_id, extra_data):
        self.event_id = event_id
        self.territory_id = territory_id
        self.extra_data = extra_data

    def update_event(self):
        """
        Update event from territory view
        ---
        :return:
        """
        self.territory.update_view()

    @property
    def archived_at(self):
        return self.event.archived_at

    @property
    def extra_data(self):
        return json.loads(self._extra_data)

    @extra_data.setter
    def extra_data(self, v):
        if isinstance(v, dict):
            self._extra_data = json.dumps(v)
            return
        if isinstance(v, str):
            self._extra_data = v
            return
        raise TypeError("Expected str or dict for event args, got {}".format(type(v)))

    extra_data = synonym("_extra_data", descriptor=extra_data)

    @property
    def serialize(self):
        return {
            'eventId': self.event_id,
            'territory': self.territory.serialize,
            'extraData': self.extra_data,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at
        }
