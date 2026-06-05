"""Mock `MockPAAdapter` — implémentation in-memory pour tests Phase A.

NE PAS utiliser en production. Sert uniquement à valider que le contrat
`PAAdapter` est respecté et que le cœur métier peut s'y brancher.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from src.facturation.adapters.pa.base import (
    PAAdapter, PALifecycleStatus, PAStatusReport, PASubmissionResult,
)


class MockPAAdapter(PAAdapter):
    """Stocke les soumissions en mémoire. Idéal pour tests unitaires/E2E."""

    def __init__(self) -> None:
        self._submissions: dict[str, dict] = {}
        self._healthy = True

    def submit_invoice(self, *, facturx_pdf: bytes, facture_numero: str,
                       artisan_id: str, client_data: dict) -> PASubmissionResult:
        if not facturx_pdf.startswith(b"%PDF-"):
            raise ValueError("facturx_pdf doit être un PDF valide")
        sub_id = f"mock-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        self._submissions[sub_id] = {
            "facture_numero": facture_numero,
            "artisan_id": artisan_id,
            "client_data": client_data,
            "pdf_size": len(facturx_pdf),
            "current_status": PALifecycleStatus.SUBMITTED,
            "submitted_at": now,
            "events": [{"status": PALifecycleStatus.SUBMITTED.value,
                        "at": now.isoformat()}],
        }
        return PASubmissionResult(
            pa_submission_id=sub_id, submitted_at=now,
            status=PALifecycleStatus.SUBMITTED,
            raw_response={"mock": True, "id": sub_id},
        )

    def get_status(self, pa_submission_id: str) -> PAStatusReport:
        sub = self._submissions.get(pa_submission_id)
        if sub is None:
            raise KeyError(f"Soumission {pa_submission_id} introuvable")
        return PAStatusReport(
            pa_submission_id=pa_submission_id,
            current_status=sub["current_status"],
            last_event_at=datetime.fromisoformat(sub["events"][-1]["at"]),
            events=list(sub["events"]),
        )

    def cancel(self, pa_submission_id: str, motif: str) -> None:
        sub = self._submissions.get(pa_submission_id)
        if sub is None:
            raise KeyError(f"Soumission {pa_submission_id} introuvable")
        if sub["current_status"] in (PALifecycleStatus.READ,
                                      PALifecycleStatus.PAID):
            raise RuntimeError("Trop tard pour annuler (déjà lue ou payée)")
        sub["current_status"] = PALifecycleStatus.REJECTED
        sub["events"].append({"status": "cancelled",
                              "at": datetime.utcnow().isoformat(),
                              "motif": motif})

    def health_check(self) -> bool:
        return self._healthy

    # Helpers test-only
    def _force_status(self, pa_submission_id: str, status: PALifecycleStatus) -> None:
        sub = self._submissions[pa_submission_id]
        sub["current_status"] = status
        sub["events"].append({"status": status.value,
                              "at": datetime.utcnow().isoformat()})
