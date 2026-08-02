"""Database layer using SQLAlchemy async with SQLite."""

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.models.schemas import Incident, IncidentStatus


class Base(DeclarativeBase):
    pass


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True)
    status = Column(String, default=IncidentStatus.OPEN.value)
    alert_data = Column(Text)  # JSON
    logs_data = Column(Text, default="[]")  # JSON
    analysis_data = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Database:
    """Async database manager."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./incidents.db"):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def init(self):
        """Create tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def save_incident(self, incident: Incident) -> None:
        """Save or update an incident."""
        async with self.async_session() as session:
            record = await session.get(IncidentRecord, incident.id)
            if record is None:
                record = IncidentRecord(
                    id=incident.id,
                    status=incident.status.value,
                    alert_data=incident.alert.model_dump_json(),
                    logs_data=json.dumps([log.model_dump() for log in incident.logs]),
                    analysis_data=incident.analysis.model_dump_json() if incident.analysis else None,
                    created_at=incident.created_at,
                    updated_at=incident.updated_at,
                )
                session.add(record)
            else:
                record.status = incident.status.value
                record.logs_data = json.dumps([log.model_dump() for log in incident.logs])
                record.analysis_data = (
                    incident.analysis.model_dump_json() if incident.analysis else None
                )
                record.updated_at = datetime.utcnow()
            await session.commit()

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Get incident by ID."""
        async with self.async_session() as session:
            return await session.get(IncidentRecord, incident_id)

    async def get_all_incidents(self, limit: int = 50) -> list[IncidentRecord]:
        """Get all incidents."""
        from sqlalchemy import select

        async with self.async_session() as session:
            result = await session.execute(
                select(IncidentRecord).order_by(IncidentRecord.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())
