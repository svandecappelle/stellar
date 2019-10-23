from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class Sector(Base):
    __tablename__ = 'sector'

    id = Column(Integer, nullable=False)  # Sector number
    name = Column(Integer, nullable=True)  # Sector generated name

    def __repr__(self):
        return '<id {}>'.format(self.id)

    @property
    def serialize(self):
        data = {
            'id': self.id,
            'name': str(self.name).strip()
        }
