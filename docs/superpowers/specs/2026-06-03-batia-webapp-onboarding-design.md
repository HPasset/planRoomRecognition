# Spec — Onboarding de la livraison ALGOR-IT (`batia-webapp`)

**Date** : 2026-06-03
**Auteur** : Hadrien Passet (batIA) avec Claude
**Statut** : En cours — Phase 0/1 non démarrée
**Périmètre** : Sécuriser la livraison ALGOR-IT, créer le repo dédié `batia-webapp`, auditer la base de code, vérifier que l'app tourne en local. **Hors périmètre** : design d'intégration ML (cycle séparé en Phase 4).

---

## 1. Contexte

La société ALGOR-IT (gitlab.com/algoritca) a livré le 2026-06-01 le code source d'une webapp constituant la première brique de batIA, utilisée actuellement en démo avec des artisans électriciens. Le livrable a été reçu sous forme d'une archive ZIP extraite dans `~/Downloads/webapp-main/`, sans historique git (le `.git` n'est pas inclus). batIA dispose d'une **cession complète des droits IP** sur ce code.

La stack livrée :
- **Backend** : Symfony 7.3, PHP ≥8.2, Doctrine ORM 3, JWT (Lexik + refresh), Flysystem S3, Messenger AMQP, WebSocket (`phrity/websocket`), PHPStan, PHPUnit, PHPCS. Dépend de deux bundles propriétaires ALGOR-IT : `aiclib/core-bundle ^1.0` et `aiclib/user-bundle ^1.0`. 114 migrations Doctrine.
- **Frontend** : React 18 + TypeScript + Vite, Chakra UI 2, dnd-kit, TanStack Query/Table, react-hook-form, i18next, react-router 6, Storybook 8, Vitest, Tailwind, pdfjs-dist.
- **Infra dev** : Docker Compose, MySQL, images poussées sur `registry.gitlab.com` (privé, requiert token GitLab).
- **Fichiers d'amorçage AI** : `AGENTS.md` présents back et front — ALGOR-IT a travaillé avec assistance d'agents IA.

Volume total : ~10 MB hors dépendances.

## 2. Objectifs

1. **Préserver la livraison** byte-exact pour traçabilité contractuelle.
2. **Créer un repo Git dédié** sur GitHub (compte HPasset), privé, pour héberger la base webapp séparément de `planRoomRecognition`.
3. **Auditer la base** sur 7 axes (qualité, sécurité, archi, perf, tests, dépendances, doc/RGPD) avec scoring 1-5 et plan de remédiation chiffré.
4. **Vérifier qu'on peut faire tourner l'app en local** avec la procédure ALGOR-IT.
5. **Préparer la transition** vers la Phase 4 (design d'intégration ML), qui sera un cycle brainstorming séparé.

## 3. Décisions structurantes (validées)

| Décision | Choix retenu | Justification |
|----------|--------------|---------------|
| Repo dédié vs intégration dans `planRoomRecognition` | **Repo dédié** | Stacks orthogonales (Python ML vs PHP/React), cycles de vie différents, IP/traçabilité |
| Plateforme git | **GitHub**, compte HPasset existant | Continuité avec `planRoomRecognition`, écosystème déjà utilisé. Org `batia` à créer plus tard si besoin |
| Visibilité repo | **Privé** | Code propriétaire batIA |
| Profondeur audit | **Audit complet** (~1,5 jour) | Première livraison externe, justifie l'investissement |
| Format livrable audit | **Markdown structuré unique** (`docs/audit/AUDIT.md`) | Versionné, partageable, lisible |
| Approche intégration ML | **Décidée après audit** | L'audit alimente le design d'intégration (entités, endpoints, file async existante) |
| IP | **Cession pleine propriété** | Permet rename composer.json, nouveau LICENSE, libre modification |

## 4. Architecture cible multi-repo

```
~/Developer/
├── planRoomRecognition/              ← existant, microservices Python ML
│   ├── src/planrec/                  ← YOLO, segmentation, pastilles, tableau
│   ├── tests/
│   └── docs/superpowers/specs/       ← ce spec vit ici
│
├── batia-webapp/                     ← NOUVEAU, Symfony + React
│   ├── backend/                      ← code ALGOR-IT
│   ├── frontend/                     ← code ALGOR-IT
│   ├── devcontainer/
│   ├── documentation/                ← doc ALGOR-IT préservée
│   ├── data/
│   ├── docs/
│   │   ├── audit/AUDIT.md            ← livrable Phase 2
│   │   ├── provenance/ALGOR-IT-handover.md
│   │   ├── provenance/local-boot-procedure.md
│   │   └── superpowers/specs/        ← copie du présent spec
│   ├── CLAUDE.md                     ← amorçage pour conversations futures
│   ├── CHANGELOG.md                  ← celui d'ALGOR-IT préservé
│   ├── README.md                     ← réécrit pour contexte batIA
│   ├── LICENSE                       ← nouveau, batIA propriétaire
│   └── Makefile                      ← celui d'ALGOR-IT préservé
│
└── batia-vendor-deliverables/        ← NOUVEAU, hors-Git
    └── algor-it-2026-06-01/          ← snapshot byte-exact, read-only
        └── (copie intégrale de webapp-main)
```

**Communication ML ↔ webapp** : à définir en Phase 4. Pistes pré-identifiées (à challenger) : microservice HTTP/REST (FastAPI) ou worker async via AMQP (le bundle `symfony/amqp-messenger` est déjà câblé).

## 5. Phases d'exécution

### Phase 0 — Préservation (~5 min)

Objectif : geler une copie byte-exact du livrable, indépendante des modifications futures.

Actions :
1. `mkdir -p ~/Developer/batia-vendor-deliverables/algor-it-2026-06-01`
2. `cp -R ~/Downloads/webapp-main/. ~/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`
3. `chmod -R a-w ~/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`
4. Vérifier intégrité : `find … -type f | wc -l` doit matcher le compte source.

**Critères d'acceptation** : dossier read-only, count fichiers OK, accessible mais non modifiable.

### Phase 1 — Bootstrap du repo `batia-webapp` (~45 min)

Objectif : un repo Git GitHub privé, premier commit propre, env local nettoyé.

Actions :
1. `cp -R ~/Downloads/webapp-main ~/Developer/batia-webapp`
2. `cd ~/Developer/batia-webapp && git init -b main`
3. **Audit `.gitignore`** : vérifier couverture `vendor/`, `node_modules/`, `var/`, `public/build/`, `.env`, `data/database/*.sql`. Compléter au besoin.
4. **Traitement `.env`** : lecture du contenu, retirer toutes valeurs sensibles, créer `.env.example` versionné (variables + descriptions), garder `.env` local non versionné. Mêmes opérations sur `backend/.env` et `frontend/.env`.
5. **Création `docs/provenance/ALGOR-IT-handover.md`** : date livraison, contact ALGOR-IT, périmètre, format livraison (ZIP), absence d'historique git, lien vers `batia-vendor-deliverables/`.
6. **Réécriture `README.md`** : contexte batIA, dépendances système, lien vers `docs/audit/AUDIT.md` (à venir), procédure boot local.
7. **Création `CLAUDE.md`** racine : amorçage assistant IA — provenance, phase courante, fichiers clés à lire, règles de manipulation (snapshot vendor read-only, copyrights ALGOR-IT à préserver dans les fichiers source du temps).
8. **Création `LICENSE`** : LICENSE propriétaire batIA (cession pleine propriété actée).
9. **Copie du présent spec** vers `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md`.
10. **Bootstrap memory** : écrire `~/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/MEMORY.md` + 1-2 fichiers de contexte (profil utilisateur, état projet) pour que Claude soit opérationnel dès la première conversation dans le nouveau dossier.
11. `git add -A && git commit -m "Initial commit from ALGOR-IT delivery (2026-06-01)"`
12. `gh repo create HPasset/batia-webapp --private --source=. --description "batIA webapp — Symfony + React (livraison ALGOR-IT 2026-06-01)"`
13. `git push -u origin main`

**Critères d'acceptation** :
- Repo GitHub privé accessible, premier commit visible
- `git log` montre 1 commit unique avec message clair
- `.env` non versionné, `.env.example` versionné
- `CLAUDE.md` présent et complet
- Spec présent dans `docs/superpowers/specs/`

**Décision à prendre par utilisateur avant Phase 1** :
- Nom exact du repo : `batia-webapp` (proposé) ou autre (`batia-app`, `select-batia`, …)
- Traitement `.env` : laisser Claude gérer selon jugement, ou inspection conjointe ?

### Phase 2 — Audit complet (~1,5 jour)

Objectif : produire `docs/audit/AUDIT.md` couvrant 7 axes avec scoring 1-5 et plan de remédiation chiffré.

**Les 7 axes audités** :

| # | Axe | Périmètre |
|---|-----|-----------|
| 1 | Architecture & organisation | Structure `backend/src/`, conventions Symfony, couplage modules. Front : structure `src/`, composants, hooks, state mgmt, routing, usage Chakra |
| 2 | Qualité de code | PHPStan (niveau, erreurs), PHPCS, complexité, duplication, dead code, dette visible. Front : ESLint, TS coverage (`any` ?), Prettier |
| 3 | Sécurité | JWT (clés/durées/refresh), CORS, validation entrées, upload S3, SQLi (Doctrine), XSS (Twig/React), `#[IsGranted]`, secrets, headers HTTP |
| 4 | Performance | N+1 Doctrine, eager/lazy loading, indexes DB, pagination, cache Symfony, bundle size, code splitting, react-query strategy |
| 5 | Tests | Couverture PHPUnit + Vitest, unit vs intégration, fixtures, CI configurée |
| 6 | Dépendances & supply chain | `composer audit`, `npm audit`, outdated, dépendances inutilisées, licences, **risque bundles AICLIB propriétaires** |
| 7 | Documentation, RGPD & DX | README, `documentation/`, AGENTS.md, CHANGELOG, ADRs, commentaires. RGPD : données perso stockées, rétention, droits. DX : onboarding clarté, Makefile |

**Outils lancés** :
- `composer audit`, `composer outdated`, `composer unused`
- `vendor/bin/phpstan analyse`, `vendor/bin/phpcs`
- `npm audit`, `npm outdated`, `npx depcheck`
- `npm run lint`, `npm run typecheck`, `npm run test:run -- --coverage`
- Lecture manuelle ciblée : auth, controllers principaux, entités cœur
- Stats : LOC par module, fichiers > 500 lignes

**Structure du rapport** :

```markdown
# Audit batia-webapp — Livrable ALGOR-IT 2026-06-01

## Synthèse exécutive
- Score global X/5
- Verdict : Intégrable tel quel / avec remédiation / refonte partielle
- Top 3 risques bloquants
- Top 3 forces

## Méthodologie & périmètre

## 1-7. Axes (un par section, avec score, forces, faiblesses, findings AUDIT-XXX)

## Plan de remédiation chiffré
| ID | Axe | Finding | Sévérité | Effort | Priorité | Blocage intégration ML ? |

## Risques spécifiques à l'intégration batIA ML
(section dédiée alimentant la Phase 4)

## Recommandations stratégiques
```

**Critères d'acceptation Phase 2** :
- `AUDIT.md` committé sur `main`
- Les 7 axes ont un score 1-5 et au moins 3 findings chacun (ou justification d'absence)
- Plan de remédiation chiffré en heures/jours
- Section dédiée « blocage intégration ML » identifie le périmètre minimal à traiter avant Phase 4

### Phase 3 — Boot local (~2-4h selon prérequis)

Objectif : prouver que l'app tourne sur la machine de Hadrien.

**Prérequis à confirmer avant** :
- Docker Desktop installé et lancé
- Token GitLab valide pour `registry.gitlab.com` (à obtenir d'ALGOR-IT si non fourni)
- Dump SQL disponible (présent dans `data/database/` ? à vérifier)
- Ports nécessaires libres

**Séquence** :
1. `cd ~/Developer/batia-webapp`
2. `echo "$GITLAB_TOKEN" | docker login registry.gitlab.com -u <nom_token> --password-stdin`
3. `make build-devcontainer && make up`
4. `docker exec -i batia-webapp-database mysql -uroot -ptiger api < data/database/<dump>.sql`
5. Validation navigateur : accueil, login, dashboard, pages de démo
6. `make test` (ou équivalent)
7. **Rédaction** `docs/provenance/local-boot-procedure.md` : commandes exactes, versions Docker/OS, problèmes rencontrés et solutions.

**Critères d'acceptation Phase 3** :
- Containers démarrent sans erreur (logs propres)
- Login fonctionne avec un user du dump
- Pages clés démo s'affichent
- Tests existants ne régressent pas
- `local-boot-procedure.md` committé

**Risque identifié à remonter dans la remédiation** : dépendance au registre Docker privé ALGOR-IT. Mitigation à plan : récupérer les Dockerfiles source et builder nos images vers GHCR (GitHub Container Registry).

### Phase 4 — Transition design intégration ML (hors présent spec)

Une fois les Phases 0-3 validées, ouverture d'un **nouveau cycle brainstorming** dans le dossier `~/Developer/batia-webapp/` :
- **Input** : section « Risques spécifiques à l'intégration batIA ML » de `AUDIT.md` + intention produit Hadrien
- **Output** : `docs/superpowers/specs/<date>-batia-ml-integration-design.md`
- **Décisions attendues** : protocole (HTTP REST vs AMQP), périmètre MVP intégration, contrat d'interface, gestion des erreurs/timeouts, stockage des résultats ML.

## 6. Risques identifiés & mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Bundles `aiclib/*` non versionnés / source indisponible | Bloquant si bug ou besoin évolution | Phase 2 axe 6 : vérifier accès source, planifier vendoring ou réécriture si non |
| Registre Docker GitLab privé ALGOR-IT | Perte d'env dev si token révoqué | Plan : récupérer Dockerfiles, push vers GHCR |
| Dump SQL absent ou contient données réelles artisans | Pas de DB de dev / risque RGPD | Vérifier en Phase 3, anonymiser si nécessaire |
| Secrets dans `.env` du livrable | Fuite si commit naïf | Phase 1 action 4 : `.env` non versionné, `.env.example` propre |
| Perte de contexte conversationnel inter-dossier | Phase 4 démarre dans le brouillard | CLAUDE.md amorce + memory bootstrap (Phase 1 actions 7+10) |
| Absence d'historique git de la livraison | Pas de blame, pas de motivations commits | Snapshot read-only (Phase 0) + provenance documentée |
| Migrations Doctrine corrompues / impossibles à rejouer | Bloque setup dev/prod | Phase 3 : test explicite `php bin/console doctrine:migrations:migrate` sur DB vide en complément du restore par dump, pour valider que la chaîne complète des 114 migrations est rejouable |

## 7. Hors périmètre explicite

- Design de l'intégration ML ↔ webapp (Phase 4 séparée)
- Mise en place CI/CD GitHub Actions (sera proposée dans la remédiation post-audit)
- Migration du registre Docker (idem)
- Réécriture des bundles AICLIB propriétaires (idem si applicable)
- Refonte UX/produit
- Tests E2E
- Mise en production / hosting
- Création d'une org GitHub `batia` (différé)

## 8. Glossaire & références

- **AICLIB** : bibliothèque interne ALGOR-IT (`aiclib/core-bundle`, `aiclib/user-bundle`)
- **AGENTS.md** : convention de fichier d'amorçage agents IA (équivalent CLAUDE.md, multi-vendor)
- **Snapshot livraison** : `~/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`
- **Spec courant** : `~/Developer/planRoomRecognition/docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md` (sera dupliqué dans `batia-webapp/docs/superpowers/specs/` en Phase 1)
