from sqlalchemy import Column, DateTime, String
from sqlalchemy.ext.declarative import declarative_base

from app.core.database import Base


class BaseModel(Base):
    __abstract__ = True

    id = Column(String, primary_key=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
