"""Page Devis : pont entre le devis généré côté Home (en session) et la
base de facturation. Liste les devis persistés et permet leur acceptation.

Workflow utilisateur :
1. Home : générer le devis (DevisGlobal en session_state)
2. Devis (cette page) : sauvegarder le devis en BDD + l'accepter
3. Factures : créer acompte/situation/solde depuis le devis accepté
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta
from decimal import Decimal

import streamlit as st

from src.facturation.db import get_session_factory
from src.facturation.models import DevisDB, DevisStatut, TypeCompteur
from src.facturation.services.artisan import get_default_artisan
from src.facturation.services.clients import create_client, list_clients
from src.facturation.services.devis import (
    accept_devis, list_devis, refuse_devis, save_devis_from_payload, send_devis,
)
from src.facturation.services.numerotation import next_numero
from src.planrec.nfc_pricing import DEFAULT_PRICES_HT
from src.planrec.nfc_rules import DevisGlobal


st.set_page_config(page_title="batIA — Devis", page_icon="📋", layout="wide")
st.title("📋 Devis")

TVA_DEFAUT = Decimal("20.00")


def _statut_value(s):
    return s.value if hasattr(s, "value") else s


def _devis_global_montant_ht(devis_global: DevisGlobal) -> Decimal:
    """Somme HT depuis DevisGlobal × DEFAULT_PRICES_HT."""
    total = Decimal("0")
    for room in devis_global.per_room:
        for eq_type, qty in room.items.items():
            price = DEFAULT_PRICES_HT.get(eq_type, 0.0)
            total += Decimal(str(price)) * Decimal(qty)
    return total.quantize(Decimal("0.01"))


def _serialize_devis_global(devis_global: DevisGlobal) -> dict:
    """Sérialise DevisGlobal (dataclass) → dict JSON-compatible.

    Convertit les Enums en str (par valeur) et conserve la structure
    par pièce pour rétro-ingénierie ultérieure.
    """
    out = {"handicap": devis_global.handicap, "per_room": []}
    for room in devis_global.per_room:
        out["per_room"].append({
            "room_id": room.room_id,
            "nfc_category": (room.nfc_category.value
                             if hasattr(room.nfc_category, "value")
                             else str(room.nfc_category)),
            "surface_m2": room.surface_m2,
            "handicap": room.handicap,
            "items": {
                (eq.value if hasattr(eq, "value") else str(eq)): qty
                for eq, qty in room.items.items()
            },
            "special_feeds_detail": list(room.special_feeds_detail),
            "notes": list(room.notes),
        })
    return out


def _find_pending_devis_in_session() -> tuple[str | None, DevisGlobal | None]:
    """Cherche un DevisGlobal dans session_state (clés `devis_global_<hash>`)."""
    for key, value in st.session_state.items():
        if not isinstance(key, str) or not key.startswith("devis_global_"):
            continue
        if isinstance(value, DevisGlobal) and value.per_room:
            img_hash = key.removeprefix("devis_global_")
            return img_hash, value
    return None, None


SessionLocal = get_session_factory()
session = SessionLocal()
try:
    artisan = get_default_artisan(session)
    if artisan is None:
        st.warning("Configure d'abord ton profil dans ⚙️ Paramètres.")
        st.stop()

    tab_list, tab_save = st.tabs([
        "📋 Devis en base", "💾 Sauvegarder le devis en cours (depuis Home)",
    ])

    # ---------------------------- TAB 1 : Liste ----------------------------
    with tab_list:
        statut_options = [s.value for s in DevisStatut]
        filtre = st.multiselect(
            "Filtrer par statut", statut_options,
            default=["brouillon", "envoye", "accepte"],
        )
        q = (session.query(DevisDB)
             .filter(DevisDB.artisan_id == artisan.id)
             .order_by(DevisDB.date_emission.desc()))
        if filtre:
            q = q.filter(DevisDB.statut.in_(filtre))
        devis_rows = q.all()

        if not devis_rows:
            st.info("Aucun devis en base pour ces filtres. "
                    "Va dans l'onglet '💾 Sauvegarder' pour persister "
                    "le devis généré sur la page Home.")
        for d in devis_rows:
            statut_val = _statut_value(d.statut)
            with st.expander(
                f"**{d.numero}** — {d.client.nom_ou_raison} — "
                f"{d.montant_ttc:.2f} € TTC — {statut_val}"
            ):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Objet** : {d.objet}")
                    st.write(f"**Émis** : {d.date_emission} | "
                             f"**Validité** : {d.date_validite}")
                    st.write(f"**HT** : {d.montant_ht:.2f} € | "
                             f"**TVA** : {d.total_tva:.2f} € | "
                             f"**TTC** : {d.montant_ttc:.2f} €")
                    if d.date_acceptation:
                        st.write(f"**Accepté le** : {d.date_acceptation}")
                with col2:
                    if statut_val == "brouillon":
                        if st.button("📤 Envoyer", key=f"send_{d.id}"):
                            send_devis(session, d.id)
                            st.rerun()
                        if st.button("✅ Accepter directement", key=f"acc_{d.id}",
                                     type="primary"):
                            accept_devis(session, d.id)
                            st.rerun()
                    elif statut_val == "envoye":
                        if st.button("✅ Accepter", key=f"acc2_{d.id}",
                                     type="primary"):
                            accept_devis(session, d.id)
                            st.rerun()
                        if st.button("❌ Refuser", key=f"ref_{d.id}"):
                            refuse_devis(session, d.id)
                            st.rerun()
                    elif statut_val == "accepte":
                        st.success("✅ Devis accepté — peut être facturé")
                        st.caption("Crée la facture dans la page 📄 Factures.")

    # -------------------- TAB 2 : Sauvegarder depuis Home ------------------
    with tab_save:
        img_hash, pending = _find_pending_devis_in_session()
        if pending is None:
            st.info(
                "Aucun devis en cours détecté dans la session. "
                "Va d'abord sur 🏠 Home, charge un plan et génère un devis."
            )
            st.stop()

        st.success(f"✓ Devis en cours détecté ({len(pending.per_room)} pièces).")
        montant_ht = _devis_global_montant_ht(pending)
        total_tva = (montant_ht * TVA_DEFAUT / Decimal("100")).quantize(Decimal("0.01"))
        montant_ttc = (montant_ht + total_tva).quantize(Decimal("0.01"))

        st.write(f"**Montant HT calculé** : {montant_ht:.2f} € · "
                 f"**TVA 20%** : {total_tva:.2f} € · "
                 f"**TTC** : {montant_ttc:.2f} €")

        with st.expander("Voir le détail par pièce"):
            for r in pending.per_room:
                cat = r.nfc_category.value if hasattr(r.nfc_category, "value") else r.nfc_category
                st.write(f"• **{r.room_id}** ({cat}) — "
                         f"{sum(r.items.values())} équipements")

        st.divider()
        st.subheader("Affecter à un client")

        clients = list_clients(session, artisan.id)

        choix_client = st.radio(
            "Client", ["Existant", "Nouveau"], horizontal=True,
        )

        client_id = None
        if choix_client == "Existant":
            if not clients:
                st.warning("Aucun client en base. Bascule sur 'Nouveau' "
                           "ou crée d'abord un client via la page 👥 Clients.")
            else:
                client_choices = {
                    f"{c.nom_ou_raison} — {c.adresse_ville}": c.id
                    for c in clients
                }
                choice = st.selectbox("Sélectionner", list(client_choices.keys()))
                client_id = client_choices[choice]
        else:
            from src.facturation.models import TypeClient
            with st.form("form_quick_client"):
                col_a, col_b = st.columns(2)
                with col_a:
                    nom = st.text_input("Nom ou raison sociale *")
                    rue = st.text_input("Rue *")
                with col_b:
                    type_c = st.radio("Type", [t.value for t in TypeClient],
                                       horizontal=True)
                    email = st.text_input("Email *")
                col_c, col_d, col_e = st.columns([1, 2, 1])
                with col_c:
                    cp = st.text_input("CP *", max_chars=5)
                with col_d:
                    ville = st.text_input("Ville *")
                with col_e:
                    pays = st.text_input("Pays", value="FR", max_chars=2)
                if st.form_submit_button("➕ Créer ce client"):
                    if not (nom and rue and cp and ville and email):
                        st.error("Champs * obligatoires")
                    else:
                        new_c = create_client(
                            session, artisan_id=artisan.id,
                            type=TypeClient(type_c), nom_ou_raison=nom,
                            adresse_rue=rue, adresse_cp=cp,
                            adresse_ville=ville, adresse_pays=pays.upper(),
                            email=email,
                        )
                        st.success(f"✓ Client {nom} créé — relance la page")
                        st.rerun()

        st.divider()
        st.subheader("Détails du devis")

        objet = st.text_input(
            "Objet du devis",
            value="Installation électrique — analyse plan batIA",
        )
        validite_jours = st.number_input(
            "Validité (jours)", min_value=30, max_value=365, value=90,
        )
        accepter_direct = st.checkbox(
            "Marquer directement comme accepté", value=True,
            help="Skippe brouillon/envoyé. Décoche si tu veux conserver "
                 "le cycle complet brouillon → envoyé → accepté.",
        )

        if st.button("💾 Sauvegarder en base", type="primary",
                     disabled=(client_id is None)):
            try:
                annee = date.today().year
                numero = next_numero(session, artisan.id, annee, TypeCompteur.DEVIS)
                devis_db = save_devis_from_payload(
                    session,
                    artisan_id=artisan.id, client_id=client_id,
                    numero=numero,
                    date_emission=date.today(),
                    date_validite=date.today() + timedelta(days=validite_jours),
                    objet=objet,
                    devis_global_json=_serialize_devis_global(pending),
                    montant_ht=montant_ht, total_tva=total_tva,
                    montant_ttc=montant_ttc,
                )
                if accepter_direct:
                    accept_devis(session, devis_db.id)
                    st.success(
                        f"✓ Devis {numero} sauvegardé et accepté. "
                        "Va dans 📄 Factures → onglet '➕ Nouvelle facture'."
                    )
                else:
                    st.success(
                        f"✓ Devis {numero} sauvegardé en brouillon. "
                        "Onglet '📋 Devis en base' pour le transitionner."
                    )
            except Exception as e:
                st.error(f"Erreur : {e}")
finally:
    session.close()
