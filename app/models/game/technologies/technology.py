import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base


class TechnologyType(enum.Enum):
    Computer = "computer"
    Optical = "optical"
    Chemistry = "chemistry"
    Alliage = "alliage"
    Energy = "energy"
    Distorsion = "distorsion"
    Atom = "atom"


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
    def all(cls, user):
        """
        Fetch all user technologies
        ---
        :param user: user
        :type user: app.models.game.user.User
        :return: List of technologies
        :rtype: list[app.models.game.technologies.Technology]
        """
        query = db.session.query(Technology).filter(cls.user_id == user.id)
        return query.all()

    @property
    def serialize(self):
        data = {
            'type': repr(self.type),
            'level': self.level,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.created_at.isoformat()
        }

        return data
