"""Tests pour schema_unifilaire (rendu PDF schéma unifilaire tableau)."""
from __future__ import annotations


def test_circuit_repere_format():
    from src.planrec.schema_unifilaire import circuit_repere
    assert circuit_repere(1, 1) == "1.1"
    assert circuit_repere(2, 3) == "2.3"


def test_agcp_constants_present():
    from src.planrec import schema_unifilaire as su
    assert su.AGCP_SENSITIVITY_MA == 500
    assert su.DEFAULT_CURVE == "C"
    assert "artisan" in su.AGCP_CONFIRM_NOTE.lower()
