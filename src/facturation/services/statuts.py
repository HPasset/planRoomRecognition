"""Machine d'état Facture + calcul dynamique de retard.

Le statut "en_retard" n'est jamais stocké, toujours dérivé depuis
date_echeance + delai_grace de l'artisan.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import (
    ActionAudit, Facture, FactureStatut,
)
from src.facturation.services.audit import log_audit


_STATUTS_EN_COURS = {
    FactureStatut.EMISE,
    FactureStatut.ENVOYEE,
    FactureStatut.PARTIELLEMENT_PAYEE,
}


def _normalize_statut(value) -> FactureStatut:
    """SQLite peut renvoyer le statut comme str brut au lieu de l'enum."""
    if isinstance(value, FactureStatut):
        return value
    return FactureStatut(value)


def is_en_retard(facture: Facture, today: Optional[date] = None) -> bool:
    """Calcule si la facture est en retard de paiement (dérivé, non stocké)."""
    if _normalize_statut(facture.statut) not in _STATUTS_EN_COURS:
        return False
    today = today or date.today()
    grace = facture.artisan.delai_grace_jours
    return today > facture.date_echeance + timedelta(days=grace)


def jours_de_retard(facture: Facture, today: Optional[date] = None) -> int:
    if _normalize_statut(facture.statut) not in _STATUTS_EN_COURS:
        return 0
    today = today or date.today()
    grace = facture.artisan.delai_grace_jours
    diff = (today - facture.date_echeance - timedelta(days=grace)).days
    return max(diff, 0)


def mark_envoyee(session: Session, facture_id: str) -> Facture:
    """Transition emise → envoyee. Stocke date_envoi."""
    f = session.get(Facture, facture_id)
    if f is None:
        raise ValueError(f"Facture {facture_id} introuvable")
    if _normalize_statut(f.statut) != FactureStatut.EMISE:
        raise ValueError(
            f"Facture doit être 'emise' pour passer à 'envoyee', "
            f"actuel : {f.statut}"
        )
    f.statut = FactureStatut.ENVOYEE
    f.date_envoi = datetime.utcnow()
    session.commit(); session.refresh(f)
    log_audit(session, f.artisan_id, "Facture", f.id, ActionAudit.ENVOI,
              details={"numero": f.numero})
    return f
