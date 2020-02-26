from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class Sector(Base):
    __tablename__ = 'sector'

    id = Column(Integer, primary_key=True)
    name = Column(Integer, nullable=True)  # Sector generated name
    galaxy_name = Column(Integer, ForeignKey("galaxy.name"), nullable=False)
    position = Column(Integer, nullable=False)

    galaxy = relationship("Galaxy", back_populates="sectors")
    systems = relationship("System", back_populates="sector")

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @property
    def serialize(self):
        data = {
            'id': self.id,
            'name': str(self.name).strip()
        }
