"""Workflow E2E : artisan → client → devis → acompte → solde → paiement."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def test_workflow_complet_acompte_solde_paiement(db_session, tmp_path):
    from src.facturation.models import (
        DevisStatut, FactureStatut, FormeJuridique, ModePaiement, TypeClient,
    )
    from src.facturation.services.artisan import create_or_update_artisan
    from src.facturation.services.clients import create_client
    from src.facturation.services.creation import create_acompte, create_solde
    from src.facturation.services.devis import save_devis_from_payload
    from src.facturation.services.emission import emit_facture
    from src.facturation.services.paiements import register_paiement
    from src.facturation.services.statuts import mark_envoyee

    # 1. Setup artisan
    artisan = create_or_update_artisan(
        db_session,
        raison_sociale="batIA Élec", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="1 r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="h@b.com",
        iban="FR7612345987650123456789014",
        mentions_assurance_decennale="MAAF n°ABC")

    # 2. Client
    client = create_client(
        db_session, artisan_id=artisan.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Jean Dupont", adresse_rue="2 r", adresse_cp="92100",
        adresse_ville="Boulogne", adresse_pays="FR",
        email="d@d.com")

    # 3. Devis accepté
    devis = save_devis_from_payload(
        db_session, artisan_id=artisan.id, client_id=client.id,
        numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="Installation 100m²",
        devis_global_json={"per_room": [], "montant_ht": "10000.00"},
        montant_ht=Decimal("10000.00"), total_tva=Decimal("2000.00"),
        montant_ttc=Decimal("12000.00"),
        statut=DevisStatut.ACCEPTE,
    )

    # 4. Acompte 30%
    acompte = create_acompte(db_session, devis.id, pourcentage=30)
    # Normalize statut (SQLite str-enum quirk)
    statut_val = acompte.statut.value if hasattr(acompte.statut, "value") else acompte.statut
    assert statut_val == "brouillon"
    assert acompte.montant_ht == Decimal("3000.00")

    emit_facture(db_session, acompte.id, archives_root=tmp_path)
    db_session.refresh(acompte)
    statut_val = acompte.statut.value if hasattr(acompte.statut, "value") else acompte.statut
    assert statut_val == "emise"
    assert acompte.pdf_path is not None

    mark_envoyee(db_session, acompte.id)
    db_session.refresh(acompte)
    statut_val = acompte.statut.value if hasattr(acompte.statut, "value") else acompte.statut
    assert statut_val == "envoyee"

    # 5. Paiement acompte
    register_paiement(
        db_session, acompte.id, Decimal("3600.00"),
        ModePaiement.VIREMENT, reference="VIR-001",
    )
    db_session.refresh(acompte)
    statut_val = acompte.statut.value if hasattr(acompte.statut, "value") else acompte.statut
    assert statut_val == "payee"

    # 6. Solde
    solde = create_solde(db_session, devis.id)
    assert solde.acompte_montant_ht == Decimal("3000.00")
    # Reste à payer : 7000 HT × 1.20 = 8400 TTC
    assert solde.montant_du_ttc == Decimal("8400.00")

    emit_facture(db_session, solde.id, archives_root=tmp_path)
    mark_envoyee(db_session, solde.id)

    # 7. Paiement solde
    register_paiement(
        db_session, solde.id, Decimal("8400.00"),
        ModePaiement.VIREMENT, reference="VIR-002",
    )
    db_session.refresh(solde)
    statut_val = solde.statut.value if hasattr(solde.statut, "value") else solde.statut
    assert statut_val == "payee"


def test_workflow_annulation_avec_avoir(db_session, tmp_path):
    from src.facturation.models import (
        DevisStatut, FactureStatut, FactureType, FormeJuridique, TypeClient,
    )
    from src.facturation.services.artisan import create_or_update_artisan
    from src.facturation.services.avoirs import cancel_facture
    from src.facturation.services.clients import create_client
    from src.facturation.services.creation import create_acompte
    from src.facturation.services.devis import save_devis_from_payload
    from src.facturation.services.emission import emit_facture

    artisan = create_or_update_artisan(
        db_session, raison_sociale="X", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    cli = create_client(db_session, artisan_id=artisan.id,
        type=TypeClient.PARTICULIER, nom_ou_raison="C", adresse_rue="r",
        adresse_cp="75001", adresse_ville="P", adresse_pays="FR",
        email="c@c.com")
    d = save_devis_from_payload(db_session, artisan_id=artisan.id,
        client_id=cli.id, numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X", devis_global_json={},
        montant_ht=Decimal("1000"), total_tva=Decimal("200"),
        montant_ttc=Decimal("1200"), statut=DevisStatut.ACCEPTE)
    f = create_acompte(db_session, d.id, pourcentage=30)
    emit_facture(db_session, f.id, archives_root=tmp_path)
    avoir = cancel_facture(db_session, f.id, motif="Erreur de calcul")

    db_session.refresh(f)
    statut_val = f.statut.value if hasattr(f.statut, "value") else f.statut
    assert statut_val == "annulee"
    type_val = avoir.type.value if hasattr(avoir.type, "value") else avoir.type
    assert type_val == "381"  # AVOIR
    assert avoir.facture_remplacee_id == f.id
    assert avoir.montant_ttc < 0
