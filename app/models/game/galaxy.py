import json
from datetime import datetime

from app.models.base import Base
from sqlalchemy import Column, Integer, VARCHAR, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship


class Galaxy(Base):
    __tablename__ = 'galaxy'

    name = Column(VARCHAR(255), primary_key=True)
    sector_number = Column(Integer, default=10, nullable=False)  # number of sectors
    properties = Column(String, nullable=True)  # galaxy generation properties

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    systems = relationship("System")

    def __init__(self, name, sector_number=10, properties: dict=None):
        self.name = name
        self.sector_number = sector_number
        self.properties = json.dumps(properties)

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
    def create(cls, session, name, sector_number=10, properties: dict=None):
        """
        Initialize the galaxy
        """
        galaxy = cls(name=name, sector_number=sector_number, properties=properties)
        session.add(galaxy)
        session.flush()

        return galaxy

    def __repr__(self):
        return '<name {}>'.format(self.name)

    @property
    def serialize(self):
        return {
            'name': str(self.name).strip(),
            'sector_number': self.sector_number,
            'properties': json.loads(self.properties)
        }
