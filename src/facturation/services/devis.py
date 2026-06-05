"""Service Devis : CRUD + transitions de statut.

`save_devis_from_payload` est l'entry-point principal pour persister un devis
qui sort du pipeline `streamlit_app.py` (la dataclass DevisGlobal est
sérialisée en JSON et stockée telle quelle).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import DevisDB, DevisStatut


def save_devis_from_payload(session: Session, **fields) -> DevisDB:
    d = DevisDB(**fields)
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def get_devis(session: Session, devis_id: str) -> Optional[DevisDB]:
    return session.get(DevisDB, devis_id)


def list_devis(session: Session, artisan_id: str,
               statut: Optional[DevisStatut] = None) -> list[DevisDB]:
    q = (session.query(DevisDB)
         .filter(DevisDB.artisan_id == artisan_id)
         .order_by(DevisDB.date_emission.desc()))
    if statut is not None:
        q = q.filter(DevisDB.statut == statut)
    return q.all()


def send_devis(session: Session, devis_id: str) -> DevisDB:
    """brouillon → envoye."""
    d = session.get(DevisDB, devis_id)
    if d is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    if d.statut != DevisStatut.BROUILLON:
        raise ValueError(f"Transition impossible depuis {d.statut.value}")
    d.statut = DevisStatut.ENVOYE
    session.commit()
    session.refresh(d)
    return d


def accept_devis(session: Session, devis_id: str) -> DevisDB:
    """envoye → accepte (verrouille le devis)."""
    d = session.get(DevisDB, devis_id)
    if d is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    if d.statut not in (DevisStatut.ENVOYE, DevisStatut.BROUILLON):
        raise ValueError(f"Transition impossible depuis {d.statut.value}")
    d.statut = DevisStatut.ACCEPTE
    d.date_acceptation = datetime.utcnow()
    session.commit()
    session.refresh(d)
    return d


def refuse_devis(session: Session, devis_id: str) -> DevisDB:
    d = session.get(DevisDB, devis_id)
    if d is None:
        raise ValueError(f"Devis {devis_id} introuvable")
    if d.statut not in (DevisStatut.ENVOYE, DevisStatut.BROUILLON):
        raise ValueError(f"Transition impossible depuis {d.statut.value}")
    d.statut = DevisStatut.REFUSE
    session.commit()
    session.refresh(d)
    return d
