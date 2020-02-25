from Crypto.Hash import SHA256
from datetime import datetime

from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    email = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    roles = relationship("Role", back_populates="user")

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def __repr__(self):
        return '<username {}>'.format(self.username)

    @classmethod
    def exists(cls, session, username):
        """
        Check if user exists
        """
        return session.query(User).filter(cls.username == username).first() is not None

    @classmethod
    def get(cls, session, username):
        """
        Get user object
        """
        return session.query(User).filter(cls.username == username).one()

    @classmethod
    def new(cls, session, username, password, email):
        usr = cls(username=username, email=email)
        encrypt = SHA256.new()
        encrypt.update(password.encode('utf-8'))
        usr.password = encrypt.digest()
        session.add(usr)
        return usr

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
