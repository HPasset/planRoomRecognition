"""Annulation de facture → génération automatique d'un Avoir (type 381)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from src.facturation.models import (
    ActionAudit, Facture, FactureLigne, FactureStatut, FactureType, TypeCompteur,
)
from src.facturation.services.audit import log_audit
from src.facturation.services.numerotation import next_numero


def cancel_facture(session: Session, facture_id: str, motif: str) -> Facture:
    """Annule la facture origine et émet un avoir (type 381) équivalent."""
    origine = session.get(Facture, facture_id)
    if origine is None:
        raise ValueError(f"Facture {facture_id} introuvable")
    if origine.statut == FactureStatut.ANNULEE:
        raise ValueError("Facture déjà annulée")
    if origine.type == FactureType.AVOIR:
        raise ValueError("Impossible d'annuler un avoir")

    annee = date.today().year
    numero_avo = next_numero(session, origine.artisan_id, annee, TypeCompteur.AVOIR)

    avoir = Facture(
        artisan_id=origine.artisan_id, client_id=origine.client_id,
        devis_id=origine.devis_id,
        facture_remplacee_id=origine.id,
        numero=numero_avo, type=FactureType.AVOIR,
        date_emission=date.today(), date_echeance=date.today(),
        objet=f"Avoir sur facture {origine.numero}",
        reference_devis=origine.reference_devis,
        motif_avoir=motif,
    )
    for ordre, l in enumerate(origine.lignes, 1):
        avoir.lignes.append(FactureLigne(
            ordre=ordre, designation=f"Avoir : {l.designation}",
            quantite=l.quantite, unite=l.unite,
            prix_unitaire_ht=-l.prix_unitaire_ht,
            montant_ht_ligne=-l.montant_ht_ligne,
            taux_tva=l.taux_tva, categorie_tva=l.categorie_tva,
        ))
    avoir.montant_ht = -origine.montant_ht
    avoir.total_tva = -origine.total_tva
    avoir.montant_ttc = -origine.montant_ttc
    avoir.montant_du_ttc = Decimal("0")

    session.add(avoir)
    origine.statut = FactureStatut.ANNULEE
    session.commit(); session.refresh(avoir)

    log_audit(session, origine.artisan_id, "Facture", origine.id,
              ActionAudit.ANNULATION, details={"motif": motif, "avoir": numero_avo})
    return avoir
