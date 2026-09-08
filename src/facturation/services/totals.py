"""Calculs HT/TVA/TTC pour Facture. Multi-taux supporté.

Arrondi HALF_EVEN (banker's) sur 2 décimales = cohérent EN16931 / DGFiP.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Iterable


_TWO = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO, rounding=ROUND_HALF_EVEN)


def compute_facture_totals(lignes: Iterable) -> dict:
    """Renvoie dict avec montant_ht, total_tva, montant_ttc, par_taux."""
    par_taux: dict[Decimal, dict[str, Decimal]] = defaultdict(
        lambda: {"base_ht": Decimal("0"), "tva": Decimal("0")}
    )
    montant_ht = Decimal("0")

    for l in lignes:
        montant_ht += l.montant_ht_ligne
        tva_ligne = _round2(l.montant_ht_ligne * l.taux_tva / Decimal("100"))
        par_taux[l.taux_tva]["base_ht"] += l.montant_ht_ligne
        par_taux[l.taux_tva]["tva"] += tva_ligne

    montant_ht = _round2(montant_ht)
    total_tva = _round2(sum((v["tva"] for v in par_taux.values()), Decimal("0")))
    montant_ttc = _round2(montant_ht + total_tva)

    par_taux_clean: dict[Decimal, dict[str, Decimal]] = {}
    for taux, vals in par_taux.items():
        par_taux_clean[taux] = {
            "base_ht": _round2(vals["base_ht"]),
            "tva": _round2(vals["tva"]),
        }

    return {
        "montant_ht": montant_ht,
        "total_tva": total_tva,
        "montant_ttc": montant_ttc,
        "par_taux": par_taux_clean,
    }
