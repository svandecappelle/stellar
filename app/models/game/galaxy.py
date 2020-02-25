from datetime import datetime

from app.models.base import Base
from sqlalchemy import Column, Integer, VARCHAR, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class Galaxy(Base):
    __tablename__ = 'galaxy'

    name = Column(VARCHAR(255), primary_key=True)
    sector_number = Column(Integer, default=10, nullable=False)  # number of sectors
    sector_size = Column(Integer, default=500, nullable=False)  # number of system in one sector

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, name, sector_size=500, sector_number=10):
        self.name = name
        self.sector_size = sector_size
        self.sector_number = sector_number

    @classmethod
    def exists(cls, session, name):
        """
        Check if galaxy exists
        """
        return session.query(Galaxy).filter(cls.name == name).first() is not None

    @classmethod
    def get(cls, session, name):
        """
        Get galaxy conf
        """
        return session.query(Galaxy).filter(cls.name == name).one()

    @classmethod
    def create(cls, session, name, sector_size=500, sector_number=10):
        """
        Initialize the galaxy
        """
        galaxy = cls(name=name, sector_size=sector_size, sector_number=sector_number)
        session.add(galaxy)
        session.flush()
        return galaxy

    def __repr__(self):
        return '<name {}>'.format(self.name)

    @property
    def serialize(self):
        return {
            'name': str(self.name).strip(),
            'sector_size': self.sector_size,
            'sector_number': self.sector_number
        }
