import hashlib
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.event import PositionalEvent, UserEvent
from app.models.game.technologies.technology import Technology
from app.models.role import Role


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    email = Column(String)

    faction_id = Column(Integer, ForeignKey("factions.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("Role", back_populates="user")
    technologies = relationship("Technology", back_populates="user")
    territories = relationship("Territory", back_populates="user")
    faction = relationship("Faction")

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def __repr__(self):
        return '<username {}>'.format(self.username)

    @classmethod
    def exists(cls, username):
        """
        Check if user exists
        """
        return db.session.query(User).filter(cls.username == username).first() is not None

    @classmethod
    def get(cls, username):
        """
        Get user object
        """
        return db.session.query(User).filter(cls.username == username).one()

    @classmethod
    def new(cls, username, password, email, territory=None):
        usr = cls(username=username, email=email)
        given = hashlib.sha256(password.encode('utf-8'))
        usr.password = given.hexdigest()
        db.session.add(usr)

        db.session.flush()
        if territory:  # If no territory the user is not a playable user (Moderator / Administrator)
            territory.assign(user=usr)
            Technology.initialize(usr)
        return usr

    def add_role(self, role_type, scope="*"):
        """
        Add a specific role to the user:
        ---
        :param role_type: Role type
        :param scope: scope of action
        """
        role = Role.create(user=self, role_type=role_type, scope=scope)
        self.roles.append(role)

    def affect_faction(self, faction):
        """
        ---
        """
        self.faction = faction

    @property
    def events(self):
        """
        ---
        :return:
        """
        return {
            'positional': PositionalEvent.all(user=self),
            'general': UserEvent.all(user=self)
        }

    def serialize(self, without_rights=True):
        data = {
            'id': self.id,
            'username': str(self.username).strip(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.created_at.isoformat()
        }
        if not without_rights:
            data['roles'] = [role.serialize for role in self.roles]

        return data
