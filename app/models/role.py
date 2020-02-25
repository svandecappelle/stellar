from datetime import datetime
import enum

from app.application import db
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
    role_type = Column(String, Enum(RoleType))
    scope = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="roles")

    def __init__(self, user_id, role_type, scope):
        self.user_id = user_id
        self.role_type = role_type.value
        self.scope = scope

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def create(cls, user, role_type, scope):
        role = cls(user_id=user.id, role_type=role_type, scope=scope)
        db.session.add(role)
        return role

    @property
    def serialize(self):
        data = {
            'user_id': self.user_id,
            'type': self.role_type,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.created_at.isoformat() if self.created_at else None
        }

        return data
