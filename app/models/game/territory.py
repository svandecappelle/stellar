from datetime import datetime

from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class Territory(Base):
    __tablename__ = 'territory'

    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, ForeignKey("system.id"), nullable=False)
    name = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    system = relationship("System", back_populates="territories")
    territory_events = relationship("PositionalEventDetail", back_populates="territory")

    def __init__(self, system):
        self.system_id = system.id

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @property
    def serialize(self):
        data = {
            'id': self.id,
            'name': str(self.name).strip(),
            'sector_id': self.sector.serialize(),
        }

        return data
