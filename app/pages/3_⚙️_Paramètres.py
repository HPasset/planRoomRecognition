"""Page paramètres artisan : SIRET, TVA, adresse, RIB, mentions légales."""
from __future__ import annotations

import streamlit as st

from src.facturation.db import get_session_factory
from src.facturation.models import FormeJuridique
from src.facturation.services.artisan import (
    create_or_update_artisan,
    get_default_artisan,
)


st.set_page_config(page_title="batIA — Paramètres", page_icon="⚙️", layout="wide")
st.title("⚙️ Paramètres artisan")

SessionLocal = get_session_factory()
session = SessionLocal()
try:
    current = get_default_artisan(session)

    with st.form("form_artisan"):
        st.subheader("Identité légale")
        col1, col2 = st.columns(2)
        with col1:
            raison_sociale = st.text_input(
                "Raison sociale", value=current.raison_sociale if current else "",
            )
            siret = st.text_input(
                "SIRET (14 chiffres)", value=current.siret if current else "",
                max_chars=14,
            )
            forme_options = [f.value for f in FormeJuridique]
            if current:
                fj = current.forme_juridique
                forme_default = fj.value if hasattr(fj, "value") else fj
            else:
                forme_default = "EI"
            forme = st.selectbox(
                "Forme juridique", forme_options,
                index=forme_options.index(forme_default),
            )
        with col2:
            numero_tva_intra = st.text_input(
                "N° TVA intra",
                value=current.numero_tva_intra if current else "",
            )
            code_naf = st.text_input(
                "Code NAF", value=(current.code_naf or "") if current else "",
            )

        st.subheader("Adresse")
        adresse_rue = st.text_input("Rue", value=current.adresse_rue if current else "")
        adresse_complement = st.text_input(
            "Complément (optionnel)",
            value=(current.adresse_complement or "") if current else "",
        )
        col3, col4, col5 = st.columns([1, 2, 1])
        with col3:
            adresse_cp = st.text_input(
                "Code postal", value=current.adresse_cp if current else "",
                max_chars=5,
            )
        with col4:
            adresse_ville = st.text_input(
                "Ville", value=current.adresse_ville if current else "",
            )
        with col5:
            adresse_pays = st.text_input(
                "Pays (ISO)", value=current.adresse_pays if current else "FR",
                max_chars=2,
            )

        st.subheader("Contact")
        col6, col7 = st.columns(2)
        with col6:
            telephone = st.text_input("Téléphone", value=(current.telephone or "") if current else "")
        with col7:
            email = st.text_input("Email", value=current.email if current else "")

        st.subheader("Banque (IBAN obligatoire pour virements clients)")
        iban = st.text_input("IBAN", value=current.iban if current else "")
        col8, col9 = st.columns(2)
        with col8:
            bic = st.text_input("BIC", value=(current.bic or "") if current else "")
        with col9:
            nom_banque = st.text_input(
                "Nom banque", value=(current.nom_banque or "") if current else "",
            )

        st.subheader("Mentions légales BTP (apparaissent sur factures)")
        mentions_decennale = st.text_area(
            "Assurance décennale (assureur + N° contrat + zone)",
            value=(current.mentions_assurance_decennale or "") if current else "",
            height=80,
        )
        mentions_biennale = st.text_area(
            "Garantie biennale (optionnel)",
            value=(current.mentions_garantie_biennale or "") if current else "",
            height=80,
        )

        st.subheader("Configuration paiement")
        delai_grace = st.number_input(
            "Délai de grâce avant 'en retard' (jours)",
            min_value=0, max_value=30,
            value=current.delai_grace_jours if current else 3,
        )

        submit = st.form_submit_button("💾 Enregistrer", type="primary")

    if submit:
        try:
            artisan = create_or_update_artisan(
                session,
                raison_sociale=raison_sociale,
                forme_juridique=FormeJuridique(forme),
                siret=siret,
                numero_tva_intra=numero_tva_intra,
                code_naf=code_naf or None,
                adresse_rue=adresse_rue,
                adresse_complement=adresse_complement or None,
                adresse_cp=adresse_cp,
                adresse_ville=adresse_ville,
                adresse_pays=adresse_pays.upper(),
                telephone=telephone or None,
                email=email,
                iban=iban,
                bic=bic or None,
                nom_banque=nom_banque or None,
                mentions_assurance_decennale=mentions_decennale or None,
                mentions_garantie_biennale=mentions_biennale or None,
                delai_grace_jours=delai_grace,
            )
            st.success(f"✓ Artisan enregistré (id={artisan.id[:8]}…)")
        except ValueError as e:
            st.error(f"Erreur de validation : {e}")
finally:
    session.close()
