# Spec — Facturation batIA Phase A (PDP-compatible day-1)

**Date** : 2026-06-05
**Auteur** : Hadrien Passet (batIA) avec Claude
**Statut** : En cours — implémentation non démarrée
**Phase** : A (sur 5 phases A → E identifiées en début de brainstorming)
**Périmètre** : Module facturation dans le prototype Streamlit `planRoomRecognition`, architecturé pour être 100% PDP-compatible dès la première facture émise. **Hors périmètre** : envoi email, intégration PPF, devenir PDP enregistré (phases B → E roadmap en section 8).

---

## 1. Contexte stratégique

batIA est un SaaS B2B pour électriciens artisans qui couvre le pipeline complet : analyse de plans → devis → étude → approvisionnement → **facturation**. La facturation est livrée par ALGOR-IT dans `batia-webapp` (Symfony+React, audit en cours, cf spec `2026-06-03-batia-webapp-onboarding-design.md`), mais on veut **développer la facturation côté prototype Streamlit en parallèle** pour valider le besoin et le data model avant intégration ALGOR-IT.

**Ambition long-terme stratégique** : batIA devient *Plateforme de Dématérialisation Partenaire* enregistrée DGFiP (statut "PDP" / "Plateforme Agréée"), pour créer un switching cost maximal et positionner batIA comme outil tout-en-un. Cette ambition (phase E) est **inatteignable en 2026** pour un fondateur solo (cf section 8), mais elle dicte les contraintes d'architecture dès la Phase A :

- Data model strictement EN16931 dès J+1
- Factur-X EN16931 (COMFORT) embarqué dans chaque facture
- Numérotation séquentielle légale (CGI art. 286)
- Hash SHA-256 + archivage propre + audit log (préparation traçabilité PDP)
- Architecture séparée (domaine / persistence / présentation) pour portabilité vers Symfony

Le chemin vers E passe par A → B → C → D. Phase A est la fondation.

## 2. Objectifs Phase A

1. Donner à l'artisan la capacité d'émettre des factures conformes Factur-X EN16931 depuis un devis batIA
2. Couvrir le pattern complet d'un chantier électrique : acompte → situations intermédiaires → solde → avenants si besoin → avoirs si annulation
3. Persister durablement les données (artisan, clients, devis, factures, paiements) dans SQLite, avec migrations versionnées prêtes pour portage vers MariaDB (Symfony/Doctrine)
4. Anticiper les contraintes PDP (intégrité, archivage, audit log) sans encore implémenter la couche PPF
5. Tests robustes pour pouvoir évoluer sans régression

## 3. Décisions structurantes validées

| Décision | Choix retenu | Justification |
|----------|--------------|---------------|
| Pattern de facturation | **Complet** : 1 devis → N factures (acompte / situations / solde + avenants) | Couvre la réalité du chantier électricien (souvent étalé sur semaines/mois) |
| Persistance | **SQLite local + SQLAlchemy 2.x ORM + Alembic** | Multi-tenant ready, portable Doctrine, migrations versionnées |
| Factur-X | **EN16931 (COMFORT) dès la 1ère facture** | PDP-compatible day-1, zéro migration de data plus tard |
| Architecture code | **Module séparé `src/facturation/`** | Isolation du module métier, portabilité vers Symfony |
| UI | **Streamlit multi-page** (`app/pages/`) | Nativement supporté, sépare proprement les domaines |
| Approche stratégique PDP | **A → B → C → D maintenant, E quand l'équipe + funding suit** | Seule trajectoire crédible vers E |

## 4. Architecture

### 4.1 Structure de code

```
src/
├── planrec/                 ← existant, inchangé
│   ├── nfc_rules.py         (DevisGlobal reste source de vérité métier)
│   ├── nfc_pricing.py
│   └── ...
└── facturation/             ← NOUVEAU
    ├── __init__.py
    ├── db.py                 SQLAlchemy engine + session factory + Base
    ├── models/
    │   ├── __init__.py
    │   ├── artisan.py        Artisan (seller party EN16931)
    │   ├── client.py         Client (buyer party EN16931)
    │   ├── devis.py          DevisDB (persisté, miroir DevisGlobal)
    │   ├── facture.py        Facture, FactureLigne, FactureStatut, FactureType
    │   ├── avenant.py        Avenant (modificatif devis)
    │   ├── paiement.py       Paiement, ModePaiement
    │   ├── avoir.py          Avoir (facture rectificative)
    │   ├── audit_log.py      AuditLog (traçabilité PDP)
    │   └── compteur.py       Compteur (numérotation par artisan/année/type)
    ├── services/
    │   ├── numerotation.py   next_numero(artisan_id, annee, type) avec lock
    │   ├── creation.py       create_facture_from_devis (acompte/situation/solde)
    │   ├── totals.py         Calculs HT/TVA/TTC, gestion multi-taux
    │   ├── statuts.py        Machine d'état + recalcul "en_retard"
    │   ├── relances.py       Détection retard, calcul jours (UI badges)
    │   ├── avenants.py       Création + signature flag + impact sur facture
    │   ├── avoirs.py         Génération d'avoir automatique sur annulation
    │   └── audit.py          log_audit(entity, action, details)
    ├── factur_x/
    │   ├── builder.py        build_xml_cii(facture) → XML EN16931
    │   ├── validator.py      validate_xsd(xml) avec schémas officiels
    │   ├── embedder.py       generate_facturx_from_binary (PDF/A-3 + XML embed)
    │   └── schemas/          XSD EN16931 officiels (versionnés)
    ├── pdf/
    │   ├── renderer.py       reportlab : rendu visuel A4 portrait
    │   ├── templates.py      Templates avec mentions légales FR
    │   └── archive.py        archive_facture(pdf, hash) + paths
    └── migrations/           Alembic (versions/ initial)
```

### 4.2 UI Streamlit multi-page

On utilise le multi-page natif Streamlit (dossier `app/pages/`) pour isoler les nouvelles fonctionnalités sans toucher au `streamlit_app.py` existant (2955 lignes qui contient déjà Devis + Pastilles + Tableau électrique).

```
app/
├── streamlit_app.py          ← actuel, INCHANGÉ (devient "🏠 Home" avec tout
│                                le pipeline Devis + Pastilles + Tableau)
└── pages/                    ← NOUVEAU dossier
    ├── 1_📄_Factures.py       NOUVEAU : liste + détail + création
    ├── 2_👥_Clients.py        NOUVEAU : référentiel clients
    └── 3_⚙️_Paramètres.py     NOUVEAU : artisan SIRET, TVA, mentions, RIB
```

Le refactor d'extraction du tableau électrique vers sa propre page est **hors périmètre Phase A** (peut être fait plus tard si utile).

### 4.3 Base de données

- **SQLite** à `data/batia.db` (gitignored, créé au premier boot via Alembic)
- **SQLAlchemy 2.x ORM** déclaratif
- **Alembic** pour migrations versionnées
- Schémas types **portable Doctrine** (pas de quirks SQLite-only : pas de `JSON1`, pas de fonctions custom)

### 4.4 Multi-tenant

- Toutes les tables ont `artisan_id` FK
- Prototype : un seul Artisan créé au premier boot via la page Paramètres
- Migration future : isolation stricte par `WHERE artisan_id = ?`, jamais cross-tenant

### 4.5 Dépendances Python ajoutées

- `sqlalchemy>=2.0`
- `alembic`
- `facturx` (PyPI) pour embed PDF/A-3 + XML
- `reportlab` (probablement déjà présent)
- `lxml` (validation XSD)
- `pydantic>=2` (sérialisation cohérente devis ↔ facture)

## 5. Modèle de données EN16931

### 5.1 Artisan (Seller party)

| Champ | Type | EN16931 | Notes |
|---|---|---|---|
| id | UUID | — | clé technique |
| raison_sociale | str | BT-27 | |
| forme_juridique | enum | — | EI / SARL / SAS / EURL / SASU |
| siret | str(14) | BT-29 | obligatoire |
| siren | str(9) | — | dérivé |
| numero_tva_intra | str | BT-31 | FR + clé + SIREN |
| code_naf | str(5) | — | activité |
| adresse_rue | str | BT-35 | |
| adresse_cp | str(5) | BT-38 | |
| adresse_ville | str | BT-37 | |
| adresse_pays | str(2) | BT-40 | FR par défaut |
| telephone, email | str | BT-42, BT-43 | |
| iban | str | BT-84 | |
| bic | str | BT-86 | |
| nom_banque | str | BT-85 | |
| mentions_assurance_decennale | text | — | obligation BTP : nom assureur + N° contrat + zone |
| mentions_garantie_biennale | text | — | |
| logo_blob | bytes | — | logo pour PDF |
| signature_blob | bytes | — | signature scannée optionnelle |

### 5.2 Client (Buyer party)

| Champ | Type | EN16931 | Notes |
|---|---|---|---|
| id | UUID | — | |
| artisan_id | FK | — | |
| type | enum | — | particulier / professionnel |
| nom_ou_raison | str | BT-44 | |
| siret | str(14)? | BT-46 | si pro |
| numero_tva_intra | str? | BT-48 | si pro intra-UE |
| adresse_rue, cp, ville, pays | str | BT-50..55 | |
| telephone, email | str | BT-58, BT-59 | |

### 5.3 DevisDB

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| artisan_id, client_id | FK | |
| numero | str | format `DEV-2026-0001` |
| date_emission | date | |
| date_validite | date | |
| objet | str | "Installation électrique maison 100m²" |
| devis_global_json | JSON | sérialisation pydantic de `DevisGlobal` (lignes par pièce, totaux) |
| montant_ht, total_tva, montant_ttc | decimal(12,2) | |
| statut | enum | brouillon / envoye / accepte / refuse / expire |
| signature_client_blob | bytes? | scan ou OTP timestamp |
| date_acceptation | datetime? | |

### 5.4 Facture (table centrale)

| Champ | Type | EN16931 | Notes |
|---|---|---|---|
| id | UUID | — | |
| artisan_id, client_id, devis_id | FK | — | `devis_id` nullable (factures hors devis) |
| numero | str | BT-1 | format `FAC-2026-0001` |
| type | enum | BT-3 | 380 standard / 386 acompte / 326 situation / 381 avoir |
| date_emission | date | BT-2 | |
| date_echeance | date | BT-9 | |
| objet | str | BT-22 | |
| devise | str(3) | BT-5 | EUR |
| montant_ht | decimal(12,2) | BT-109 | |
| total_tva | decimal(12,2) | BT-110 | |
| montant_ttc | decimal(12,2) | BT-112 | |
| acompte_montant_ht | decimal(12,2) | BT-114 | acomptes cumulés précédents |
| montant_du_ttc | decimal(12,2) | BT-115 | reste à payer |
| statut | enum | — | brouillon / emise / envoyee / partiellement_payee / payee / en_retard / annulee |
| date_envoi | datetime? | — | |
| date_paiement | datetime? | — | |
| mode_paiement | enum | BT-81 | 30 virement / 20 chèque / 48 CB / 10 espèces |
| conditions_paiement | text | BT-20 | "Paiement à 30 jours" |
| reference_devis | str? | BT-13 | numéro du devis source |
| pdf_path | str | — | chemin PDF/A-3 |
| facturx_xml_path | str | — | chemin XML CII |
| hash_sha256 | str | — | empreinte du PDF (intégrité) |
| facture_remplacee_id | FK? | — | si avoir : facture rectifiée |

### 5.5 FactureLigne

| Champ | Type | EN16931 |
|---|---|---|
| id | UUID | — |
| facture_id | FK | — |
| ordre | int | — |
| designation | str | BT-153 |
| quantite | decimal(12,4) | BT-129 |
| unite | enum | BT-130 (C62 unité / HUR heure / MTR mètre / H87 pièce / JOU jour) |
| prix_unitaire_ht | decimal(12,4) | BT-146 |
| montant_ht_ligne | decimal(12,2) | BT-131 |
| taux_tva | decimal(5,2) | BT-152 (20.00 / 10.00 / 5.50 / 0.00) |
| categorie_tva | enum | BT-151 (S / AA / Z / E) |
| reference_article | str? | BT-155 |

### 5.6 Avenant

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| devis_origine_id | FK | |
| numero | str | format `AVE-2026-0001` |
| date | date | |
| objet | str | "Ajout 3 prises Cuisine, déplacement tableau" |
| lignes_supplementaires_json | JSON | DevisLignes additionnelles (positif ou négatif) |
| montant_ht_supplementaire | decimal | peut être négatif |
| signature_client_blob | bytes? | |
| date_acceptation | datetime? | |

### 5.7 Paiement

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| facture_id | FK | |
| montant | decimal(12,2) | partiel possible |
| date | date | |
| mode | enum | virement / chèque / CB / espèces |
| reference | str | n° chèque, ID virement |
| commentaire | text? | |

### 5.8 Compteur (numérotation séquentielle)

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| artisan_id | FK | |
| annee | int | |
| type | enum | DEV / FAC / AVO / AVE |
| valeur_courante | int | dernier numéro attribué |

Contrainte unique : `(artisan_id, annee, type)`.

### 5.9 AuditLog

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| artisan_id | FK | |
| entity_type | enum | Facture / Devis / Avenant / Paiement |
| entity_id | UUID | |
| action | enum | CREATION / EMISSION / ENVOI / ANNULATION / PAIEMENT / MODIFICATION |
| timestamp | datetime | |
| details_json | JSON | infos contextuelles (hash, montant, etc.) |

### 5.10 Catégories TVA gérées dès Phase A

- **S 20%** : standard électricité neuve
- **AA 10%** : rénovation logement >2 ans
- **AA 5.5%** : rénovation énergétique (CEE, MaPrimeRénov)
- **Z 0%** : autoliquidation BTP B2B (avec mention obligatoire au PDF)

Mixte autorisé dans la même facture, récapitulatif TVA par taux (BT-118..119).

## 6. Flux métier

### 6.1 Cycle de vie du Devis

```
brouillon ─[envoi]─→ envoye ─[acceptation client]─→ accepte ─→ (factures créées)
                       │                       └─[refus]─────→ refuse
                       └─[date_validite dépassée]────────────→ expire
```

**Règles** :
- Devis modifiable uniquement en `brouillon` ou `envoye`
- Une fois `accepte`, devis verrouillé : modifications passent par un **Avenant**
- Création de factures autorisée uniquement si `accepte` (acompte autorisé dès `envoye` pour réservation chantier)

### 6.2 Cycle de vie de la Facture

```
brouillon ─[validation]─→ emise ─[envoi]─→ envoyee ──┐
                                                       ├─[paiement partiel]─→ partiellement_payee
                                                       └─[paiement total]────→ payee

envoyee ─[date_echeance + delai_grace dépassés]─→ en_retard (dérivé, pas stocké)
                                                       │
                                                       └─[paiement]─→ payee

toute_facture ─[annulation]─→ annulee  (génère systématiquement un Avoir)
```

**Règles** :
- `brouillon` éditable. Une fois `emise` : immutable côté contenu, seul le statut évolue
- `emise → envoyee` : transition manuelle Phase A (bouton "Marquer comme envoyée"). Phase D : auto via PPF
- `en_retard` : **calculé dynamiquement** à chaque chargement, non persisté
- `annulee` : numéro reste utilisé (séquence continue). Avoir auto pour annulation comptable

### 6.3 Actions disponibles depuis un Devis `accepte`

**1. Créer un acompte** (type 386)
- Montant : % du devis HT (défaut 30%) OU montant libre
- Désignation auto : "Acompte sur devis DEV-2026-XXXX"
- Une ligne, taux TVA = taux moyen pondéré du devis (ou 20% par défaut)
- Mise à jour `acomptes_cumules` du devis

**2. Créer une facture de situation** (type 326)
- L'artisan saisit l'avancement par lot (% ou montant par poste)
- Lignes générées depuis le devis × pourcentage avancement
- Acomptes précédents déduits dans BT-114
- Mise à jour cumul

**3. Créer le solde** (type 380)
- Calcul auto : `montant_total_devis - somme(acomptes + situations)`
- Lignes du devis complet, déduction des acomptes en bas
- Émission possible uniquement si devis 100% facturé après cette opération

**4. Créer un Avoir** (type 381)
- Réfère à une facture existante (`facture_remplacee_id`)
- Lignes négatives ou identiques au choix
- Motif obligatoire (BT-116 : "Annulation client", "Erreur de facturation", etc.)

### 6.4 Avenants (modification de devis en cours de chantier)

- Créé depuis un Devis `accepte`
- Lignes additionnelles (ou retrait avec montant négatif)
- Signature client requise (Phase A : flag "Accepté par client" + date, sans signature numérique)
- Une fois accepté : modifie le `montant_total_facturable` du devis pour les factures suivantes

### 6.5 Numérotation : implémentation

```python
def next_numero(session, artisan_id, annee, type):
    # SQLite : BEGIN EXCLUSIVE empêche les writes concurrents (suffit pour
    # solo prototype). Migration PostgreSQL/MariaDB future = SELECT ... FOR UPDATE.
    session.execute(text("BEGIN EXCLUSIVE"))
    compteur = session.query(Compteur).filter_by(
        artisan_id=artisan_id, annee=annee, type=type,
    ).with_for_update().first()
    if compteur is None:
        compteur = Compteur(artisan_id=artisan_id, annee=annee,
                            type=type, valeur_courante=0)
        session.add(compteur)
    compteur.valeur_courante += 1
    session.commit()
    return f"{type}-{annee}-{compteur.valeur_courante:04d}"
```

Format : `DEV / FAC / AVO / AVE`.

Numérotation **attribuée à la création**, pas à l'envoi. Un brouillon `FAC-2026-0042` jeté = nécessite un Avoir pour comblement (séquence continue respectée).

### 6.6 Calcul "en retard"

Dérivé à chaque chargement : `today > date_echeance + delai_grace AND statut IN (emise, envoyee, partiellement_payee)`.

- `delai_grace` configurable par artisan (défaut 3 jours)
- Affichage UI : badge rouge + nombre de jours
- Phase B : déclenche relances auto

## 7. Génération Factur-X EN16931 + PDF/A-3

### 7.1 Pile technique

| Brique | Lib | Rôle |
|---|---|---|
| Rendu visuel PDF | **reportlab** | template A4 avec mentions légales FR |
| XML CII EN16931 | **lxml** + Jinja2 templates | construction du flux XML conforme |
| Embed XML dans PDF/A-3 | **facturx** (PyPI) | PDF/A-3 avec XML attaché + métadonnées XMP |
| Validation XSD | **lxml** + schémas EN16931 officiels | validation à la génération |
| Hash | **hashlib** | SHA-256 du PDF pour intégrité |

### 7.2 Pipeline de génération

```
Facture (DB) ─→ build_xml_cii(facture) ─→ XML EN16931
                                            │
                                            ├─→ validate_xsd(xml)
                                            │       │
                                            │       └─[fail]─→ erreur, blocage émission
                                            │
                          render_pdf(facture) ─→ PDF visuel
                                            │
                          generate_facturx(pdf, xml) ─→ PDF/A-3 + XML embarqué
                                            │
                          archive_facture(pdf) ─→ hash SHA-256 + path
                                            │
                          DB Facture mise à jour : pdf_path, facturx_xml_path, hash_sha256
                                            │
                          Statut : brouillon → emise (verrouillage)
                                            │
                          AuditLog : action EMISSION + details
```

### 7.3 Profile XML : EN 16931 (COMFORT)

Conformité minimum pour Factur-X B2B (tolère B2C). En-tête XML clé :

```xml
<rsm:ExchangedDocumentContext>
  <ram:BusinessProcessSpecifiedDocumentContextParameter>
    <ram:ID>A1</ram:ID>  <!-- Réforme française 2026 -->
  </ram:BusinessProcessSpecifiedDocumentContextParameter>
  <ram:GuidelineSpecifiedDocumentContextParameter>
    <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
  </ram:GuidelineSpecifiedDocumentContextParameter>
</rsm:ExchangedDocumentContext>
```

Tous les champs `BT-*` listés en section 5 sont renseignés depuis le data model. Le builder utilise Jinja2 + validation lxml.

### 7.4 Rendu visuel PDF (template reportlab)

Zones (A4 portrait) :
- **En-tête** : Logo artisan + raison sociale + adresse + SIRET + TVA intra
- **Bloc destinataire** : Client (nom + adresse)
- **Titre + méta** : "FACTURE N° FAC-2026-0001" / Date / Référence devis / Échéance
- **Tableau lignes** : Désignation / Qté / Unité / PU HT / TVA / Montant HT
- **Récap TVA** : par taux si multi-taux
- **Totaux** : Total HT / TVA / Total TTC / Acomptes / Net à payer
- **Conditions paiement** : IBAN/BIC / Mode / Échéance / Pénalités de retard
- **Mentions légales** : Assurance décennale + Garantie biennale + Médiation conso (B2C) + L441-10 (pénalités)

### 7.5 PDF/A-3 + Embed XML

```python
from facturx import generate_facturx_from_binary

pdf_a3 = generate_facturx_from_binary(
    pdf_bytes,
    xml_bytes,
    level="en16931",
    flavor="factur-x",
    afrelationship="Data",
)
```

Sortie : PDF/A-3 conforme, archivable, ouvrable dans tout PDF reader.

### 7.6 Archivage et intégrité

- **Dossier** : `data/factures/<artisan_id>/<annee>/<numero>.pdf`
- **Hash SHA-256** calculé à l'émission, stocké dans `Facture.hash_sha256`
- **Read-only après émission** : pas de regénération possible (sauf émission d'avoir)
- **AuditLog** : chaque changement de statut, paiement, etc. tracé
- **Pas de signature XAdES** en Phase A (Phase C/D)

### 7.7 Validation à la génération (algo)

```python
def emit_facture(facture_id):
    facture = db.get(Facture, facture_id)
    validate_facture_pre_emission(facture)    # SIRET, totaux cohérents
    xml = build_xml_cii(facture)
    validate_xsd(xml, "EN16931-CII.xsd")      # lève si non conforme
    pdf = render_pdf(facture)
    pdf_a3 = generate_facturx_from_binary(pdf, xml, level="en16931")
    path = archive(pdf_a3, facture)
    facture.pdf_path = path
    facture.hash_sha256 = sha256(pdf_a3)
    facture.statut = FactureStatut.EMISE
    log_audit(facture, "EMISSION", details={"hash": facture.hash_sha256})
    db.commit()
    return facture
```

Si XSD échoue : **blocage de l'émission** + erreur précise à l'utilisateur.

## 8. Tests

| Niveau | Couverture | Outil |
|---|---|---|
| Unit | Models, services (numérotation, calculs, machine d'état, création), builders XML | pytest |
| Intégration DB | Migrations Alembic, fixtures, contraintes (séquence, FK) | pytest + SQLite in-memory |
| Conformité Factur-X | XSD EN16931 sur chaque type (380/386/326/381) | pytest + lxml |
| PDF | Génération + parsing pypdf, métadonnées XMP, XML embarqué, hash | pytest + pypdf + facturx.check_facturx_xsd |
| UI Streamlit | Pages factures/clients/paramètres, flux E2E | streamlit AppTest |

Cible : **≥85% sur `services/` et `factur_x/`**, ≥70% sur `models/` et UI.

## 9. Hors périmètre Phase A

| Sujet | Pourquoi pas maintenant |
|---|---|
| Envoi email auto | Nécessite SMTP + templates. Phase B. Phase A : bouton "Télécharger PDF" |
| Relances automatiques | Phase B. Phase A : badges visuels jours de retard |
| Intégration PPF | Phase D (statut PDP) |
| Signature XAdES dans XML | Phase C/D, conformité PDP stricte |
| Tableau de bord financier | Phase B |
| Export comptable (FEC, Sage, Cegid, EBP) | Phase B |
| Multi-devise | Toujours EUR (data model le supporte, UI ne propose pas) |
| Auto-facturation (type 389) | Cas marginal, hors scope |
| Modèles de lignes réutilisables | Phase B |
| Auth multi-utilisateur réelle | Streamlit = single-user. Multi-user = webapp ALGOR-IT |
| Avoir partiel par ligne | Phase A : avoir global. Phase B : par ligne |

## 10. Roadmap esquissée B → E

**Phase B — Suivi & gestion avancée** (~2 semaines, après A)
- Tableau de bord financier (CA, créances, prévisions)
- Filtres avancés, recherche
- Envoi email avec templates (SendGrid ou SMTP)
- Relances auto J+7/J+15/J+30/contentieux
- Export FEC + intégrations Sage/Cegid/EBP
- Modèles de lignes réutilisables
- Multi-utilisateur prototype (préparation port webapp)

**Phase C — Conformité Factur-X stricte + signatures** (~1-2 semaines)
- Signature XAdES dans XML
- Validation officielle DGFiP
- Profile EXTENDED pour B2B exigeants
- Archivage 10 ans renforcé

**Phase D — Intégration PDP partenaire** (1-3 mois)
- Choix partenaire : Pennylane / Sage / Cegid / Lemonway / PDP indé
- API d'envoi/réception via leur infra qui parle au PPF
- batIA = *client* d'un PDP, gain marché immédiat réforme 2026-09

**Phase E — batIA devient PDP enregistré DGFiP** (12-24 mois, 2027-2028)
- Pré-requis : équipe (RSSI, devs EDI, compliance), ISO 27001, cautionnement, fonds (€1M+ Seed)
- Dossier DGFiP (cahier des charges, audit, validation)
- Migration des données et clients du PDP partenaire
- Switching cost maximal : batIA gère le bout-en-bout

## 11. Critères d'acceptation Phase A

L'artisan peut :
- Saisir ses paramètres (SIRET, TVA, mentions, IBAN) une fois
- Créer un client (particulier ou pro)
- Depuis un devis accepté : créer un acompte / situation / solde / avoir
- Générer un avenant à un devis accepté
- Émettre une facture → PDF/A-3 avec Factur-X EN16931 embarqué
- Voir la liste de ses factures, filtrer par statut, voir les en retard
- Enregistrer un paiement (partiel ou total)
- Marquer une facture comme envoyée / annulée
- Télécharger le PDF à tout moment
- Tous les XML générés passent la validation XSD EN16931

Couverture tests **≥85%** sur les couches métier critiques (services, factur_x). UI testée via streamlit AppTest pour les flux principaux.

## 12. Risques identifiés

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Évolution du cahier des charges DGFiP (réforme 2026 retardée plusieurs fois) | Re-spec partielle | Architecture modulaire, conformité incrémentale C/D |
| Lib `facturx` peu maintenue / disparaît | Blocage embed PDF/A-3 | Code de fallback avec génération PDF/A-3 manuelle via lxml + reportlab |
| Coexistence DevisGlobal (dataclass runtime) ↔ DevisDB (table) | Double source de vérité, sync casse | DevisDB = sérialisation pydantic de DevisGlobal, point de vérité unique |
| SQLite verrou DB sous charge (multi-instances Streamlit) | Numérotation duplique | Mode WAL + lock applicatif sur Compteur. Pour multi-user vrai = migration PostgreSQL/MariaDB |
| TVA multi-taux + acomptes : calcul délicat | Erreurs de TVA = problème fiscal | Tests unitaires exhaustifs sur `totals.py`, jeux de tests EN16931 officiels |
| Numérotation rompue par bug | Sanction DGFiP | Lock applicatif strict, tests dédiés, audit log de chaque attribution |
| Portage SQLAlchemy → Doctrine (port futur Symfony) | Schéma divergent | Schéma types standards, pas de SQLite-only ; champs Doctrine-compatibles ; doc des contraintes |
| Mauvaise interprétation d'un BT-* EN16931 | Refus de la facture par client / outil compta | Validation XSD systématique + relecture par expert compta si possible avant beta |

## 13. Glossaire & références

- **EN16931** : norme européenne du format de facturation électronique (CEN, 2017)
- **Factur-X** : format hybride PDF/A-3 + XML CII embarqué (FR/DE)
- **CII** : Cross Industry Invoice (UN/CEFACT, standard XML)
- **PDP** : Plateforme de Dématérialisation Partenaire (statut DGFiP)
- **PPF** : Portail Public de Facturation (infrastructure DGFiP)
- **BT-*** : Business Term (identifiants des champs EN16931, ex BT-1 = numéro facture)
- **DGFiP** : Direction Générale des Finances Publiques
- **Spec sœur** : `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md` (onboarding ALGOR-IT webapp où facturation sera portée plus tard)
