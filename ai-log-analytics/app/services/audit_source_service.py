from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import create_engine

from app.core.config import settings
from app.schemas import AuditLogEntry


def fetch_recent_audit_logs(limit: int = 200) -> list[AuditLogEntry]:
    engine = create_engine(
        settings.sqlalchemy_database_uri,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )
    since = datetime.now(timezone.utc) - timedelta(minutes=settings.recent_window_minutes)

    query = text(
        """
        SELECT
            a.user_id::text AS user_id,
            u.email AS user_email,
            a.vmid AS vmid,
            a.action::text AS action,
            a.details AS details,
            a.created_at AS created_at
        FROM audit_logs AS a
        LEFT JOIN "user" AS u ON u.id = a.user_id
        WHERE a.created_at >= :since
        ORDER BY a.created_at DESC
        LIMIT :limit
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(query, {"since": since, "limit": limit}).mappings().all()

    return [
        AuditLogEntry(
            user_id=row.get("user_id"),
            user_email=row.get("user_email"),
            vmid=row.get("vmid"),
            action=str(row.get("action") or "unknown"),
            details=str(row.get("details") or ""),
            created_at=row.get("created_at"),
        )
        for row in rows
    ]
