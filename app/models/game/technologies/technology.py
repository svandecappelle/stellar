from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.event import PositionalEvent, PositionalEventType
from app.models.game.technologies.technology_type import TechnologyType


class Technology(Base):
    __tablename__ = 'user_technologies'

    type = Column(Enum(TechnologyType), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)

    level = Column(Integer)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="technologies")

    def __init__(self, type, user_id, level, created_at=None, updated_at=None):
        self.type = type
        self.user_id = user_id
        self.level = level
        if created_at:
            self.created_at = created_at
        if updated_at:
            self.updated_at = updated_at

    @classmethod
    def initialize(cls, user):
        """
        Initialize technologies for new user
        ---
        :param user: user
        :type user: app.models.game.user.User
        :return: List of technologies
        :rtype: list[app.models.game.technologies.Technology]
        """
        for tech in TechnologyType:
            t_db = Technology(
                type=tech,
                user_id=user.id,
                level=0
            )
            db.session.add(t_db)
            db.session.flush()

    @classmethod
    def get(cls, user, type):
        """
        ---
        :param user: user
        :type user: app.models.game.user.User
        :param type: type of technology
        :type type: app.models.game.technologies.technology.TechnologyType
        :return: The technology pointed by the type for the user
        :rtype: app.models.game.technologies.Technology
        """
        return cls.query(user=user, type=type).one()

    @classmethod
    def all(cls, user):
        """
        Fetch all technologies of user
        ---
        :param user: user
        :type user: app.models.game.user.User
        :return: list of technologies
        """
        return cls.query(user=user).all()

    @classmethod
    def query(cls, user, type=None):
        """
        Fetch all user technologies using filters
        ---
        :param type:
        :param user: user
        :type user: app.models.game.user.User
        :return: query matching criteria
        """
        query = db.session.query(Technology).filter(cls.user_id == user.id)
        if type:
            query = query.filter(cls.type == type)
        return query

    def can_be_increased(self):
        """
        Check if technology is able to be increased
        ---
        :return:
        """
        # check prerequisites and resource available
        p = self.type.price(self.level + 1)
        return True

    def increase(self, territory, now=False):
        """
        Increase level of the technology
        ---
        :return:
        """
        if not now:
            return PositionalEvent.create(
                territory=territory,
                user=self.user,
                duration=self.next_level_duration,
                event_type=PositionalEventType.technology,
                extra_args=self.type
            )
        self.level += 1

    @property
    def next_level_duration(self):
        """
        Get the duration of the next level of technology
        ---
        :return: duration in seconds
        """
        return self.type.duration(self.level)

    @property
    def serialize(self):
        data = {
            'type': str(self.type),
            'level': self.level,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.created_at.isoformat()
        }

        return data
