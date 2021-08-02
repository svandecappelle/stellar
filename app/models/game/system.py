from datetime import datetime


from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.application import db
from app.models.base import Base
from app.models.game.sector import Sector


class System(Base):
    __tablename__ = 'system'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    position = Column(Integer, nullable=False)

    sector_id = Column(Integer, ForeignKey("sector.id"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    sector = relationship("Sector", back_populates="systems")
    territories = relationship("Territory", back_populates="system")

    def __init__(self, sector, position):
        self.position = position
        self.sector_id = sector.id

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @classmethod
    def get_or_create(cls, sector_id, position):
        """
        ---
        :return:
        """
        query = db.session.query(System)\
            .filter(cls.sector_id == sector_id)\
            .filter(cls.position == position)

        system = query.first()
        if not system:
            system = System(
                sector=Sector.get(id=sector_id),
                position=position
            )
            db.session.add(system)
            db.session.flush()
        return system    

    @property
    def serialize(self):
        data = {
            'id': self.id,
            'position': self.position,
            'name': self.name,
            'sector': self.sector.serialize,
        }

        return data
