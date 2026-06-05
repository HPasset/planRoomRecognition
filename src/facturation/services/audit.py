"""Helper pour écrire des entrées d'audit log."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from src.facturation.models import ActionAudit, AuditLog


def log_audit(session: Session, artisan_id: str, entity_type: str,
              entity_id: str, action: ActionAudit,
              details: Optional[dict[str, Any]] = None) -> AuditLog:
    entry = AuditLog(
        artisan_id=artisan_id, entity_type=entity_type, entity_id=entity_id,
        action=action, details_json=details or {},
    )
    session.add(entry); session.commit(); session.refresh(entry)
    return entry
