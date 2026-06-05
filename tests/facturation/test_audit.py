from __future__ import annotations


def test_log_audit_basic(db_session):
    from src.facturation.services.audit import log_audit
    from src.facturation.models import Artisan, FormeJuridique, ActionAudit, AuditLog
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    db_session.add(a); db_session.commit(); db_session.refresh(a)

    entry = log_audit(db_session, a.id, "Facture", "fake-id",
                      ActionAudit.EMISSION, details={"key": "value"})
    assert entry.id is not None
    assert entry.action == ActionAudit.EMISSION
    assert entry.details_json == {"key": "value"}

    # Check persistence
    found = db_session.query(AuditLog).filter(AuditLog.entity_id == "fake-id").first()
    assert found is not None
