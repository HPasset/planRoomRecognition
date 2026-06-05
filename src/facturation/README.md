# Module facturation batIA — Phase A

Module séparé pour la facturation Factur-X EN16931 dans le prototype Streamlit.
batIA = **passerelle vers un PA (Plateforme Agréée) tiers** — pas PDP elle-même.

## Architecture

- `db.py` — engine + session SQLAlchemy + Base déclarative
- `models/` — entités SQLAlchemy (Artisan, Client, DevisDB, Facture+Ligne,
  Avenant, Paiement, AuditLog, Compteur) + enums
- `services/` — couche métier (numérotation, totaux, creation, statuts,
  emission, avenants, avoirs, paiements, audit)
- `factur_x/` — builder XML CII EN16931 + validator + embedder PDF/A-3
- `pdf/` — renderer reportlab + archive SHA-256
- `migrations/` — Alembic versionné (5 migrations 0001..0005)

## Quickstart dev

```bash
# Setup DB (1ère fois)
.venv/bin/alembic upgrade head

# Lancer Streamlit
.venv/bin/streamlit run app/streamlit_app.py
```

Aller dans la sidebar : ⚙️ Paramètres → saisir SIRET/TVA/IBAN → 👥 Clients →
créer un client → 🏠 Home → générer un devis → puis 📄 Factures pour créer la
facture.

## Tests

```bash
.venv/bin/pytest tests/facturation/ -v
.venv/bin/pytest tests/facturation/ --cov=src/facturation
```

## Conformité

- **EN16931** : profile COMFORT (BT-1 à BT-155 essentiels)
- **Factur-X** : PDF/A-3 avec XML CII embarqué (process A1 réforme FR 2026)
- **CGI art. 286** : numérotation séquentielle non rupturée

## Hors périmètre Phase A

Cf `docs/superpowers/specs/2026-06-05-facturation-phase-a-design.md` §9 :
- Email envoi (Phase B)
- Relances auto (Phase B)
- Intégration concrète avec un PA (Phase D)
- Signature XAdES (déléguée au PA)
- Tableau de bord financier (Phase B)
- Devenir PDP DGFiP (hors stratégie batIA)
