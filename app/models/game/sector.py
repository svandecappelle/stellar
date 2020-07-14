from datetime import datetime

from app.application import db
from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class Sector(Base):
    __tablename__ = 'sector'

    id = Column(Integer, primary_key=True)
    name = Column(Integer, nullable=True)  # Sector generated name
    galaxy_name = Column(String, ForeignKey("galaxy.name"), nullable=False)
    position = Column(Integer, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    galaxy = relationship("Galaxy", back_populates="sectors")
    systems = relationship("System", back_populates="sector")

    def __init__(self, position, galaxy_name):
        self.position = position
        self.galaxy_name = galaxy_name

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def initialize_all(cls, galaxy):
        for idx in range(1, galaxy.sector_number + 1):
            sector = Sector(galaxy_name=galaxy.name, position=idx)
            db.session.add(sector)
            db.session.flush()

    @classmethod
    def get(cls, id):
        """
        ---
        :return:
        """
        return db.session.query(Sector).filter(cls.id == id).one()

    @property
    def serialize(self):
        data = {
            'id': self.id,
            'name': self.name,
            'galaxy': self.galaxy.serialize,
            'position': self.position
        }
