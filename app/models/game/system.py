from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship


class System(Base):
    __tablename__ = 'systems'

    id = Column(Integer, primary_key=True)
    sector_id = Column(Integer, nullable=False)
    name = Column(String, nullable=True)

    # sector = relationship()

    def __init__(self, sector):
        self.sector_id = sector.id

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
