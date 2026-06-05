"""Numérotation séquentielle non-rupturée par (artisan, année, type).

Conformité CGI art. 286 : pas de saut, séquence chronologique continue.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.facturation.models import Compteur, TypeCompteur


def next_numero(session: Session, artisan_id: str, annee: int,
                type: TypeCompteur) -> str:
    """Incrémente puis renvoie le numéro formaté `{TYPE}-{ANNEE}-{0000}`.

    Concurrence : SQLite single-writer suffit pour le prototype. Migration
    PostgreSQL/MariaDB : ajouter `SELECT ... FOR UPDATE` (déjà supporté
    par with_for_update() ci-dessous, transparent sur SQLite).
    """
    compteur = (session.query(Compteur)
                .filter(Compteur.artisan_id == artisan_id,
                        Compteur.annee == annee,
                        Compteur.type == type)
                .with_for_update()
                .one_or_none())
    if compteur is None:
        compteur = Compteur(
            artisan_id=artisan_id, annee=annee, type=type, valeur_courante=0,
        )
        session.add(compteur)
        session.flush()
    compteur.valeur_courante += 1
    session.commit()
    return f"{type.value}-{annee}-{compteur.valeur_courante:04d}"
