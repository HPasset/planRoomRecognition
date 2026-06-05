"""Page Clients : liste + création + édition."""
from __future__ import annotations

import streamlit as st

from src.facturation.db import get_session_factory
from src.facturation.models import TypeClient
from src.facturation.services.artisan import get_default_artisan
from src.facturation.services.clients import (
    create_client, delete_client, list_clients, update_client,
)


st.set_page_config(page_title="batIA — Clients", page_icon="👥", layout="wide")
st.title("👥 Référentiel clients")

SessionLocal = get_session_factory()
session = SessionLocal()
try:
    artisan = get_default_artisan(session)
    if artisan is None:
        st.warning("Tu dois d'abord créer ton profil dans la page ⚙️ Paramètres.")
        st.stop()

    tab_list, tab_create = st.tabs(["📋 Liste", "➕ Nouveau client"])

    with tab_list:
        clients = list_clients(session, artisan.id)
        if not clients:
            st.info("Aucun client pour l'instant.")
        else:
            for c in clients:
                with st.expander(f"{c.nom_ou_raison} — {c.adresse_ville} ({c.type.value})"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Type** : {c.type.value}")
                        st.write(f"**Adresse** : {c.adresse_rue}, {c.adresse_cp} {c.adresse_ville}")
                        st.write(f"**Email** : {c.email}")
                        if c.telephone:
                            st.write(f"**Téléphone** : {c.telephone}")
                        if c.siret:
                            st.write(f"**SIRET** : {c.siret}")
                        if c.numero_tva_intra:
                            st.write(f"**TVA intra** : {c.numero_tva_intra}")
                    with col2:
                        if st.button("🗑️ Supprimer", key=f"del_{c.id}"):
                            delete_client(session, c.id)
                            st.rerun()

    with tab_create:
        with st.form("form_client"):
            type_client = st.radio(
                "Type", [t.value for t in TypeClient], horizontal=True,
            )
            nom = st.text_input("Nom ou raison sociale *")
            col_a, col_b = st.columns(2)
            with col_a:
                siret = st.text_input("SIRET (si pro)")
            with col_b:
                tva = st.text_input("N° TVA intra (si pro)")

            rue = st.text_input("Rue *")
            col_c, col_d, col_e = st.columns([1, 2, 1])
            with col_c:
                cp = st.text_input("CP *", max_chars=5)
            with col_d:
                ville = st.text_input("Ville *")
            with col_e:
                pays = st.text_input("Pays", value="FR", max_chars=2)

            col_f, col_g = st.columns(2)
            with col_f:
                email = st.text_input("Email *")
            with col_g:
                tel = st.text_input("Téléphone")

            if st.form_submit_button("➕ Créer", type="primary"):
                if not nom or not rue or not cp or not ville or not email:
                    st.error("Champs marqués * obligatoires")
                else:
                    try:
                        create_client(
                            session, artisan_id=artisan.id,
                            type=TypeClient(type_client), nom_ou_raison=nom,
                            siret=siret or None, numero_tva_intra=tva or None,
                            adresse_rue=rue, adresse_cp=cp, adresse_ville=ville,
                            adresse_pays=pays.upper(),
                            telephone=tel or None, email=email,
                        )
                        st.success("✓ Client créé")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Erreur : {e}")
finally:
    session.close()
