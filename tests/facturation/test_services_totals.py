from __future__ import annotations
from decimal import Decimal


def test_compute_ligne_amounts():
    from src.facturation.services.totals import compute_ligne_montant
    assert compute_ligne_montant(Decimal("10"), Decimal("25.00")) == Decimal("250.00")
    assert compute_ligne_montant(Decimal("3"), Decimal("3.333")) == Decimal("10.00")


def test_compute_facture_totals_simple():
    from src.facturation.services.totals import compute_facture_totals
    from src.facturation.models import FactureLigne, CategorieTVA, UniteFacturation
    lignes = [
        FactureLigne(ordre=1, designation="A", quantite=Decimal("10"),
            unite=UniteFacturation.PIECE, prix_unitaire_ht=Decimal("25"),
            montant_ht_ligne=Decimal("250.00"),
            taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD),
        FactureLigne(ordre=2, designation="B", quantite=Decimal("5"),
            unite=UniteFacturation.PIECE, prix_unitaire_ht=Decimal("40"),
            montant_ht_ligne=Decimal("200.00"),
            taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD),
    ]
    totals = compute_facture_totals(lignes)
    assert totals["montant_ht"] == Decimal("450.00")
    assert totals["total_tva"] == Decimal("90.00")
    assert totals["montant_ttc"] == Decimal("540.00")
    assert totals["par_taux"] == {Decimal("20.00"): {
        "base_ht": Decimal("450.00"), "tva": Decimal("90.00")
    }}


def test_compute_facture_totals_multi_taux():
    from src.facturation.services.totals import compute_facture_totals
    from src.facturation.models import FactureLigne, CategorieTVA, UniteFacturation
    lignes = [
        FactureLigne(ordre=1, designation="20%", quantite=Decimal("1"),
            unite=UniteFacturation.UNITE, prix_unitaire_ht=Decimal("100"),
            montant_ht_ligne=Decimal("100.00"),
            taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD),
        FactureLigne(ordre=2, designation="10%", quantite=Decimal("1"),
            unite=UniteFacturation.UNITE, prix_unitaire_ht=Decimal("100"),
            montant_ht_ligne=Decimal("100.00"),
            taux_tva=Decimal("10.00"), categorie_tva=CategorieTVA.STANDARD),
    ]
    t = compute_facture_totals(lignes)
    assert t["montant_ht"] == Decimal("200.00")
    assert t["total_tva"] == Decimal("30.00")
    assert t["montant_ttc"] == Decimal("230.00")
    assert t["par_taux"][Decimal("20.00")]["tva"] == Decimal("20.00")
    assert t["par_taux"][Decimal("10.00")]["tva"] == Decimal("10.00")
