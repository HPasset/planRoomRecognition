"""Tests du contrat PAAdapter + MockPAAdapter."""
from __future__ import annotations
import pytest


def test_mock_submit_valid_pdf():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    from src.facturation.adapters.pa.base import PALifecycleStatus
    adapter = MockPAAdapter()
    result = adapter.submit_invoice(
        facturx_pdf=b"%PDF-1.4\nfake", facture_numero="FAC-2026-0001",
        artisan_id="artisan-1", client_data={"name": "Jean Dupont"},
    )
    assert result.pa_submission_id.startswith("mock-")
    assert result.status == PALifecycleStatus.SUBMITTED


def test_mock_submit_invalid_pdf_raises():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    adapter = MockPAAdapter()
    with pytest.raises(ValueError, match="PDF valide"):
        adapter.submit_invoice(
            facturx_pdf=b"not a pdf", facture_numero="FAC-2026-0001",
            artisan_id="a", client_data={},
        )


def test_mock_get_status_after_submit():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    adapter = MockPAAdapter()
    r = adapter.submit_invoice(
        facturx_pdf=b"%PDF-1.4\nx", facture_numero="FAC",
        artisan_id="a", client_data={},
    )
    report = adapter.get_status(r.pa_submission_id)
    assert report.pa_submission_id == r.pa_submission_id
    assert len(report.events) == 1


def test_mock_cancel_avant_lecture():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    from src.facturation.adapters.pa.base import PALifecycleStatus
    adapter = MockPAAdapter()
    r = adapter.submit_invoice(
        facturx_pdf=b"%PDF-1.4\nx", facture_numero="FAC",
        artisan_id="a", client_data={},
    )
    adapter.cancel(r.pa_submission_id, motif="Erreur côté client")
    report = adapter.get_status(r.pa_submission_id)
    assert report.current_status == PALifecycleStatus.REJECTED


def test_mock_cancel_apres_lecture_refuse():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    from src.facturation.adapters.pa.base import PALifecycleStatus
    adapter = MockPAAdapter()
    r = adapter.submit_invoice(
        facturx_pdf=b"%PDF-1.4\nx", facture_numero="FAC",
        artisan_id="a", client_data={},
    )
    adapter._force_status(r.pa_submission_id, PALifecycleStatus.READ)
    with pytest.raises(RuntimeError, match="Trop tard"):
        adapter.cancel(r.pa_submission_id, motif="X")


def test_mock_health_check():
    from src.facturation.adapters.pa.mock import MockPAAdapter
    assert MockPAAdapter().health_check() is True


def test_paadapter_is_abstract():
    from src.facturation.adapters.pa.base import PAAdapter
    with pytest.raises(TypeError, match="abstract"):
        PAAdapter()
