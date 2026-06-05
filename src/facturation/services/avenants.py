"""Création + acceptation d'avenants à un devis accepté."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.facturation.models import (
    ActionAudit, Avenant, DevisDB, DevisStatut, TypeCompteur,
)
from src.facturation.services.audit import log_audit
from src.facturation.services.numerotation import next_numero


def create_avenant(session: Session, devis_id: str, objet: str,
                   lignes_supplementaires: dict[str, Any],
                   montant_ht_supplementaire: Decimal,
                   notes: Optional[str] = None) -> Avenant:
    devis = session.get(DevisDB, devis_id)
    if devis is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    if devis.statut != DevisStatut.ACCEPTE:
        raise ValueError(
            f"Devis doit être 'accepte' pour créer un avenant, "
            f"actuel : {devis.statut if isinstance(devis.statut, str) else devis.statut.value}"
        )

    annee = date.today().year
    numero = next_numero(session, devis.artisan_id, annee, TypeCompteur.AVENANT)

    a = Avenant(
        devis_origine_id=devis_id, numero=numero,
        date_emission=date.today(), objet=objet,
        lignes_supplementaires_json=lignes_supplementaires,
        montant_ht_supplementaire=montant_ht_supplementaire,
        notes=notes,
    )
    session.add(a); session.commit(); session.refresh(a)
    log_audit(session, devis.artisan_id, "Avenant", a.id,
              ActionAudit.AVENANT_CREE,
              details={"numero": numero, "devis_origine": devis.numero})
    return a


def accept_avenant(session: Session, avenant_id: str,
                   signature: Optional[bytes] = None) -> Avenant:
    a = session.get(Avenant, avenant_id)
    if a is None:
        raise ValueError(f"Avenant {avenant_id} introuvable")
    a.date_acceptation = datetime.utcnow()
    if signature:
        a.signature_client_blob = signature
    session.commit(); session.refresh(a)
    log_audit(session, a.devis.artisan_id, "Avenant", a.id,
              ActionAudit.AVENANT_ACCEPTE, details={})
    return a
