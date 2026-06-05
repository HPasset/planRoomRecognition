from __future__ import annotations


def _artisan(s):
    from src.facturation.models import Artisan, FormeJuridique
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    s.add(a); s.commit(); s.refresh(a); return a


def test_create_client(db_session):
    from src.facturation.services.clients import create_client
    from src.facturation.models import TypeClient
    a = _artisan(db_session)
    c = create_client(db_session, artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Jean", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="j@j.com")
    assert c.id is not None


def test_list_clients_by_artisan(db_session):
    from src.facturation.services.clients import create_client, list_clients
    from src.facturation.models import TypeClient
    a = _artisan(db_session)
    create_client(db_session, artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="A", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="a@a.com")
    create_client(db_session, artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="B", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="b@b.com")
    clients = list_clients(db_session, artisan_id=a.id)
    assert len(clients) == 2
    assert {c.nom_ou_raison for c in clients} == {"A", "B"}


def test_update_client(db_session):
    from src.facturation.services.clients import create_client, update_client
    from src.facturation.models import TypeClient
    a = _artisan(db_session)
    c = create_client(db_session, artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Original", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="o@o.com")
    update_client(db_session, c.id, nom_ou_raison="Modifié")
    db_session.refresh(c)
    assert c.nom_ou_raison == "Modifié"
