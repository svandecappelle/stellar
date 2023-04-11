import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base


class System(Base):
    __tablename__ = 'system'

    id = Column(Integer, primary_key=True)
    galaxy_name = Column(String, ForeignKey("galaxy.name"), nullable=False)

    name = Column(String, nullable=True)
    # TODO insert position in vector3 representation
    # and display properties to ensure all users get same image of system
    # could be done using a jsonb for characteristics and str:'x-y-z' for vector
    position = Column(String, nullable=False)

    # We use json as text here to be sure compatible with all dbs.
    # This should not be necessary to query rows using this field
    characteristics = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    territories = relationship("Territory", back_populates="system")

    def __init__(self, galaxy, position, characteristics={}):
        self.galaxy_name = galaxy.name
        self.position = position
        self.characteristics = json.dumps(characteristics)

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def get(cls, galaxy, id):
        """
        ---
        :return:
        """
        query = db.session.query(System)\
            .filter(cls.id == id)

        system = query.one()
        return system

    @classmethod
    def create(cls, galaxy, position, characteristics=None):
        """
        ---
        :return:
        """
        system = System(
            galaxy=galaxy,
            position=position,
            characteristics=characteristics
        )
        db.session.add(system)
        db.session.flush()
        return system

    @property
    def serialize(self):
        coordinates = self.position.split("_") if self.position else [0, 0, 0]
        data = {
            'id': self.id,
            'galaxy': self.galaxy_name,
            'position': {
                'x': float(coordinates[0]),
                'y': float(coordinates[1]),
                'z': float(coordinates[2]),
            } if self.position else None,
            'name': self.name,
            'characteristics': json.loads(self.characteristics)
        }

        return data
