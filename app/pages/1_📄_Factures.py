"""Page Factures : liste filtrable, détail, actions (émettre, marquer envoyée,
enregistrer paiement, annuler, créer acompte/solde depuis devis)."""
from __future__ import annotations

from decimal import Decimal

import streamlit as st

from src.facturation.db import get_session_factory
from src.facturation.models import (
    DevisDB, DevisStatut, Facture, FactureStatut, FactureType, ModePaiement,
)
from src.facturation.services.artisan import get_default_artisan
from src.facturation.services.avoirs import cancel_facture
from src.facturation.services.creation import (
    create_acompte, create_situation, create_solde,
)
from src.facturation.services.emission import emit_facture
from src.facturation.services.paiements import register_paiement
from src.facturation.services.statuts import (
    jours_de_retard, mark_envoyee,
)


st.set_page_config(page_title="batIA — Factures", page_icon="📄", layout="wide")
st.title("📄 Factures")

SessionLocal = get_session_factory()
session = SessionLocal()
try:
    artisan = get_default_artisan(session)
    if artisan is None:
        st.warning("Configure d'abord ton profil dans ⚙️ Paramètres.")
        st.stop()

    tab_list, tab_create = st.tabs(["📋 Liste", "➕ Nouvelle facture"])

    with tab_list:
        # Filtre par statut (toutes les valeurs hors EN_RETARD qui est dérivé)
        statut_options = ["brouillon", "emise", "envoyee", "partiellement_payee",
                          "payee", "annulee"]
        filtre_statut = st.multiselect(
            "Filtrer par statut", statut_options,
            default=["brouillon", "emise", "envoyee", "partiellement_payee"],
        )
        q = (session.query(Facture)
             .filter(Facture.artisan_id == artisan.id)
             .order_by(Facture.date_emission.desc()))
        if filtre_statut:
            q = q.filter(Facture.statut.in_(filtre_statut))
        factures = q.all()

        if not factures:
            st.info("Aucune facture pour ces critères.")

        for f in factures:
            # statut peut être enum ou str selon SQLite
            statut_val = f.statut.value if hasattr(f.statut, "value") else f.statut
            retard = jours_de_retard(f)
            badge = " 🔴 RETARD" if retard > 0 else ""
            with st.expander(
                f"**{f.numero}** — {f.client.nom_ou_raison} — "
                f"{f.montant_ttc:.2f}€ TTC — {statut_val}{badge}"
            ):
                col1, col2 = st.columns([2, 1])
                with col1:
                    type_val = f.type.value if hasattr(f.type, "value") else f.type
                    st.write(f"**Type** : {type_val} | **Émise** : {f.date_emission} | "
                             f"**Échéance** : {f.date_echeance}")
                    st.write(f"**Objet** : {f.objet}")
                    if f.reference_devis:
                        st.write(f"**Réf. devis** : {f.reference_devis}")
                    if retard > 0:
                        st.error(f"En retard de {retard} jours")

                with col2:
                    if f.pdf_path:
                        try:
                            with open(f.pdf_path, "rb") as fp:
                                st.download_button(
                                    "📥 PDF", data=fp.read(),
                                    file_name=f"{f.numero}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{f.id}",
                                )
                        except FileNotFoundError:
                            st.warning("PDF introuvable sur disque")

                # Actions selon statut
                if statut_val == "brouillon":
                    if st.button("📤 Émettre (génère Factur-X)", key=f"emit_{f.id}",
                                 type="primary"):
                        try:
                            emit_facture(session, f.id)
                            st.success("Facture émise + Factur-X généré")
                            st.rerun()
                        except (ValueError, Exception) as e:
                            st.error(f"Erreur : {e}")

                if statut_val == "emise":
                    if st.button("✉️ Marquer comme envoyée", key=f"send_{f.id}"):
                        mark_envoyee(session, f.id)
                        st.rerun()

                if statut_val in ("envoyee", "partiellement_payee"):
                    with st.form(f"paiement_{f.id}"):
                        st.write("**Enregistrer un paiement**")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            montant = st.number_input(
                                "Montant (€)", min_value=0.01,
                                value=float(f.montant_du_ttc), step=10.0,
                                key=f"pay_montant_{f.id}",
                            )
                        with col_b:
                            mode = st.selectbox(
                                "Mode", [m.name for m in ModePaiement],
                                key=f"pay_mode_{f.id}",
                            )
                        ref = st.text_input("Référence", key=f"pay_ref_{f.id}")
                        if st.form_submit_button("💰 Enregistrer"):
                            register_paiement(
                                session, f.id, Decimal(str(montant)),
                                ModePaiement[mode], reference=ref or None,
                            )
                            st.rerun()

                type_val_str = f.type.value if hasattr(f.type, "value") else f.type
                if statut_val != "annulee" and type_val_str != "381":  # 381 = AVOIR
                    with st.form(f"cancel_{f.id}"):
                        motif = st.text_input("Motif annulation", key=f"motif_{f.id}")
                        if st.form_submit_button("🗑️ Annuler (génère avoir)"):
                            if not motif:
                                st.error("Motif obligatoire")
                            else:
                                cancel_facture(session, f.id, motif)
                                st.rerun()

    with tab_create:
        st.write("Sélectionne un devis accepté pour créer une facture.")
        devis_acceptes = (session.query(DevisDB)
                          .filter(DevisDB.artisan_id == artisan.id,
                                  DevisDB.statut == DevisStatut.ACCEPTE.value)
                          .all())
        if not devis_acceptes:
            st.info("Aucun devis accepté. Va dans 🏠 Home, génère un devis et marque-le accepté.")
        else:
            devis_choices = {f"{d.numero} — {d.client.nom_ou_raison} "
                             f"({d.montant_ttc:.2f}€)": d for d in devis_acceptes}
            choice = st.selectbox("Devis", list(devis_choices.keys()))
            d = devis_choices[choice]

            type_facture = st.radio(
                "Type de facture", ["Acompte", "Situation", "Solde"], horizontal=True,
            )
            if type_facture == "Acompte":
                pct = st.number_input("Pourcentage (%)", min_value=1, max_value=99, value=30)
                if st.button("➕ Créer facture d'acompte", type="primary"):
                    try:
                        f = create_acompte(session, d.id, pourcentage=int(pct))
                        st.success(f"Facture {f.numero} créée en brouillon")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Erreur : {e}")
            elif type_facture == "Situation":
                pct = st.number_input("Avancement (%)", min_value=1, max_value=100, value=50)
                desig = st.text_input("Désignation", value="Facture de situation")
                if st.button("➕ Créer facture de situation", type="primary"):
                    try:
                        f = create_situation(session, d.id, int(pct), designation=desig)
                        st.success(f"Facture {f.numero} créée en brouillon")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Erreur : {e}")
            elif type_facture == "Solde":
                if st.button("➕ Créer facture de solde", type="primary"):
                    try:
                        f = create_solde(session, d.id)
                        st.success(f"Facture {f.numero} créée en brouillon")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Erreur : {e}")
finally:
    session.close()
