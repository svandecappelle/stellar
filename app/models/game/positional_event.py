from datetime import datetime

from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class PositionalEventDetail(Base):
    __tablename__ = 'event_detail'

    event_id = Column(Integer, ForeignKey('positional_event.id'), primary_key=True)
    territory_id = Column(Integer, ForeignKey('territory.id'), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data = Column(String(2500))

    territory = relationship("Territory", back_populates="territory_events")
    event = relationship("PositionalEvent", back_populates="on_territory")


class PositionalEvent(Base):
    __tablename__ = 'positional_event'

    id = Column(Integer, primary_key=True)
    on_territory_id = Column(Integer, ForeignKey("territory.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    on_territory = relationship("PositionalEventDetail", back_populates="event")

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
