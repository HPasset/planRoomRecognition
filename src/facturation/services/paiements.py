"""Enregistrement des paiements et mise à jour du statut de facture."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import (
    ActionAudit, Facture, FactureStatut, ModePaiement, Paiement,
)
from src.facturation.services.audit import log_audit


def register_paiement(session: Session, facture_id: str, montant: Decimal,
                      mode: ModePaiement, date_paiement: Optional[date] = None,
                      reference: Optional[str] = None,
                      commentaire: Optional[str] = None) -> Paiement:
    facture = session.get(Facture, facture_id)
    if facture is None:
        raise ValueError(f"Facture {facture_id} introuvable")
    if facture.statut == FactureStatut.ANNULEE:
        raise ValueError("Facture annulée : pas de paiement possible")

    p = Paiement(
        facture_id=facture_id, montant=montant,
        date=date_paiement or date.today(), mode=mode,
        reference=reference, commentaire=commentaire,
    )
    session.add(p); session.flush()

    paiements = (session.query(Paiement)
                 .filter(Paiement.facture_id == facture_id).all())
    total_paye = sum((pp.montant for pp in paiements), Decimal("0"))

    if total_paye >= facture.montant_ttc:
        facture.statut = FactureStatut.PAYEE
        facture.date_paiement = datetime.utcnow()
    elif total_paye > Decimal("0"):
        facture.statut = FactureStatut.PARTIELLEMENT_PAYEE

    session.commit(); session.refresh(p)
    log_audit(session, facture.artisan_id, "Facture", facture.id,
              ActionAudit.PAIEMENT,
              details={"montant": str(montant), "mode": mode.value})
    return p
