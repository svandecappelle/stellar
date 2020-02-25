from datetime import datetime
import enum

from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship


class RoleType(enum.Enum):
    admin = "admin"
    moderator = "moderator"


class Role(Base):
    __tablename__ = 'user_roles'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    type = Column(String, Enum(RoleType))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="roles")

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @property
    def serialize(self):
        data = {
            'user_id': self.user_id,
            'type': self.type,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.created_at.isoformat() if self.created_at else None
        }

        return data
