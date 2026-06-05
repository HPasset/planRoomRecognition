"""Création de factures depuis un devis : acompte, situation, solde."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import (
    CategorieTVA, DevisDB, DevisStatut, Facture, FactureLigne, FactureType,
    TypeCompteur, UniteFacturation,
)
from src.facturation.services.numerotation import next_numero
from src.facturation.services.totals import compute_facture_totals


_TVA_DEFAUT = Decimal("20.00")


def _calc_echeance(emission: date, jours: int = 30) -> date:
    return emission + timedelta(days=jours)


def _check_devis_accepte(devis: DevisDB) -> None:
    if devis.statut != DevisStatut.ACCEPTE:
        raise ValueError(
            f"Devis {devis.numero} doit être 'accepte', "
            f"actuellement '{devis.statut.value}'"
        )


def _somme_factures_existantes(session: Session, devis_id: str) -> Decimal:
    factures = (session.query(Facture)
                .filter(Facture.devis_id == devis_id,
                        Facture.type != FactureType.AVOIR)
                .all())
    return sum((f.montant_ht for f in factures), Decimal("0"))


def _round_decimal2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


def create_acompte(session: Session, devis_id: str,
                   pourcentage: Optional[int] = None,
                   montant_ht: Optional[Decimal] = None) -> Facture:
    """Crée une facture d'acompte type 386 EN16931 depuis le devis."""
    devis = session.get(DevisDB, devis_id)
    if devis is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    _check_devis_accepte(devis)

    if pourcentage is not None:
        acompte_ht = (devis.montant_ht * Decimal(pourcentage) / Decimal(100)
                      ).quantize(Decimal("0.01"))
    elif montant_ht is not None:
        acompte_ht = Decimal(montant_ht).quantize(Decimal("0.01"))
    else:
        raise ValueError("Fournir pourcentage OU montant_ht")

    annee = date.today().year
    numero = next_numero(session, devis.artisan_id, annee, TypeCompteur.FACTURE)

    f = Facture(
        artisan_id=devis.artisan_id, client_id=devis.client_id, devis_id=devis.id,
        numero=numero, type=FactureType.ACOMPTE,
        date_emission=date.today(),
        date_echeance=_calc_echeance(date.today()),
        objet=f"Acompte sur devis {devis.numero}",
        reference_devis=devis.numero,
    )
    f.lignes.append(FactureLigne(
        ordre=1,
        designation=f"Acompte ({pourcentage}%)" if pourcentage else "Acompte",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=acompte_ht, montant_ht_ligne=acompte_ht,
        taux_tva=_TVA_DEFAUT, categorie_tva=CategorieTVA.STANDARD,
    ))
    totals = compute_facture_totals(f.lignes)
    f.montant_ht = totals["montant_ht"]
    f.total_tva = totals["total_tva"]
    f.montant_ttc = totals["montant_ttc"]
    f.montant_du_ttc = totals["montant_ttc"]

    session.add(f); session.commit(); session.refresh(f)
    return f


def create_situation(session: Session, devis_id: str,
                     pourcentage_avancement: int,
                     designation: str = "Facture de situation") -> Facture:
    """Crée une facture de situation type 326. Acomptes précédents déduits."""
    devis = session.get(DevisDB, devis_id)
    if devis is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    _check_devis_accepte(devis)

    montant_situation_ht = (
        devis.montant_ht * Decimal(pourcentage_avancement) / Decimal(100)
    ).quantize(Decimal("0.01"))
    acomptes_cumules = _somme_factures_existantes(session, devis_id)
    montant_du_ht = max(montant_situation_ht - acomptes_cumules, Decimal("0"))

    annee = date.today().year
    numero = next_numero(session, devis.artisan_id, annee, TypeCompteur.FACTURE)

    f = Facture(
        artisan_id=devis.artisan_id, client_id=devis.client_id, devis_id=devis.id,
        numero=numero, type=FactureType.SITUATION,
        date_emission=date.today(),
        date_echeance=_calc_echeance(date.today()),
        objet=designation, reference_devis=devis.numero,
        acompte_montant_ht=acomptes_cumules,
    )
    f.lignes.append(FactureLigne(
        ordre=1,
        designation=f"{designation} — {pourcentage_avancement}% du devis {devis.numero}",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=montant_situation_ht, montant_ht_ligne=montant_situation_ht,
        taux_tva=_TVA_DEFAUT, categorie_tva=CategorieTVA.STANDARD,
    ))
    totals = compute_facture_totals(f.lignes)
    f.montant_ht = totals["montant_ht"]
    f.total_tva = totals["total_tva"]
    f.montant_ttc = totals["montant_ttc"]
    f.montant_du_ttc = _round_decimal2(
        montant_du_ht * (Decimal("1") + _TVA_DEFAUT / Decimal("100"))
    )

    session.add(f); session.commit(); session.refresh(f)
    return f


def create_solde(session: Session, devis_id: str) -> Facture:
    """Crée la facture de solde type 380 = devis complet - acomptes cumulés."""
    devis = session.get(DevisDB, devis_id)
    if devis is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    _check_devis_accepte(devis)

    acomptes_cumules = _somme_factures_existantes(session, devis_id)
    annee = date.today().year
    numero = next_numero(session, devis.artisan_id, annee, TypeCompteur.FACTURE)

    f = Facture(
        artisan_id=devis.artisan_id, client_id=devis.client_id, devis_id=devis.id,
        numero=numero, type=FactureType.STANDARD,
        date_emission=date.today(),
        date_echeance=_calc_echeance(date.today()),
        objet=f"Solde — {devis.objet}",
        reference_devis=devis.numero,
        acompte_montant_ht=acomptes_cumules,
    )
    f.lignes.append(FactureLigne(
        ordre=1,
        designation=f"Solde des travaux — devis {devis.numero}",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=devis.montant_ht, montant_ht_ligne=devis.montant_ht,
        taux_tva=_TVA_DEFAUT, categorie_tva=CategorieTVA.STANDARD,
    ))
    totals = compute_facture_totals(f.lignes)
    f.montant_ht = totals["montant_ht"]
    f.total_tva = totals["total_tva"]
    f.montant_ttc = totals["montant_ttc"]
    montant_du_ht = max(f.montant_ht - acomptes_cumules, Decimal("0"))
    f.montant_du_ttc = _round_decimal2(
        montant_du_ht * (Decimal("1") + _TVA_DEFAUT / Decimal("100"))
    )

    session.add(f); session.commit(); session.refresh(f)
    return f
