# batia-webapp Bootstrap (Phases 0 + 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Préserver la livraison ALGOR-IT byte-exact, créer le repo Git dédié `batia-webapp` privé sur GitHub avec un premier commit propre, et amorcer le contexte Claude pour les conversations futures dans ce nouveau dossier.

**Architecture :** Phase 0 = copie figée read-only du livrable hors-Git. Phase 1 = nouveau dossier `~/Developer/batia-webapp/` initialisé en Git, sécurisation des secrets, ajout des artefacts batIA (CLAUDE.md, provenance, spec, LICENSE), push vers GitHub privé. Commits atomiques séparant strictement le contenu ALGOR-IT original (commit 1) de nos ajouts (commits 2-N) pour traçabilité IP/contractuelle.

**Tech Stack :** Bash, git, gh CLI, file system. Pas de code applicatif touché.

**Spec source :** `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md`

**Conventions :**
- Tous les chemins absolus
- `SOURCE` = `/Users/hadrienpasset/Downloads/webapp-main`
- `VENDOR_DIR` = `/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01`
- `REPO` = `/Users/hadrienpasset/Developer/batia-webapp`
- `MEMORY_DIR` = `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory`
- `GH_USER` = `HPasset`
- `REPO_NAME` = `batia-webapp`

---

## Task 1 : Préservation byte-exact du livrable (Phase 0)

**Files:**
- Create: `/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/` (dossier read-only)

- [ ] **Step 1 : Compter les fichiers source pour comparaison ultérieure**

Run:
```bash
find /Users/hadrienpasset/Downloads/webapp-main -type f | wc -l
```
Expected : un nombre N (probablement ~5000-10000 incluant `node_modules` n'existe pas car non installé ; en réalité ~500-1500). **Noter ce nombre N pour Step 4.**

- [ ] **Step 2 : Créer le dossier vendor et copier**

Run:
```bash
mkdir -p /Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01
cp -R /Users/hadrienpasset/Downloads/webapp-main/. /Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/
```
Expected : pas de sortie d'erreur. La commande `cp -R src/. dst/` copie le **contenu** de src dans dst (incluant fichiers cachés comme `.gitignore`, `.env`, `.editorconfig`).

- [ ] **Step 3 : Mettre en read-only**

Run:
```bash
chmod -R a-w /Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01
```
Expected : pas de sortie d'erreur.

- [ ] **Step 4 : Vérifier intégrité (count + tentative d'écriture)**

Run:
```bash
find /Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01 -type f | wc -l
touch /Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/.test-write 2>&1 || echo "READ_ONLY_OK"
```
Expected :
- Premier `wc -l` retourne le même N qu'en Step 1
- `touch` doit échouer ET afficher `READ_ONLY_OK` (le `|| echo` se déclenche sur erreur)

**Si le count diffère** : investiguer (fichiers cachés ratés ?) avant de continuer.

---

## Task 2 : Créer la copie de travail `batia-webapp` + init Git

**Files:**
- Create: `/Users/hadrienpasset/Developer/batia-webapp/` (copie de travail)

- [ ] **Step 1 : Vérifier qu'aucun dossier existant ne porte ce nom**

Run:
```bash
test -d /Users/hadrienpasset/Developer/batia-webapp && echo "EXISTS_STOP" || echo "OK_TO_CREATE"
```
Expected : `OK_TO_CREATE`. **Si `EXISTS_STOP`** : ne pas écraser, demander à l'utilisateur.

- [ ] **Step 2 : Copier le livrable vers le dossier de travail**

Run:
```bash
cp -R /Users/hadrienpasset/Downloads/webapp-main /Users/hadrienpasset/Developer/batia-webapp
```
Expected : pas d'erreur. Le `cp -R src dst` (sans `/.`) crée `dst` et y copie `src` (donc on aura `batia-webapp/` contenant la même chose que `webapp-main/`).

- [ ] **Step 3 : Vérifier que la copie est bien indépendante de `vendor-deliverables/`**

Run:
```bash
ls -la /Users/hadrienpasset/Developer/batia-webapp | head -5
test -w /Users/hadrienpasset/Developer/batia-webapp && echo "WRITABLE_OK" || echo "NOT_WRITABLE_BAD"
```
Expected : `WRITABLE_OK` (cette copie doit être modifiable).

- [ ] **Step 4 : Initialiser git sur la branche `main`**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git init -b main
```
Expected : `Initialized empty Git repository in /Users/hadrienpasset/Developer/batia-webapp/.git/`

- [ ] **Step 5 : Configurer git localement (si nécessaire)**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git config --local user.email "hadrien.passet@gmail.com" && git config --local user.name "HPasset"
```
Expected : pas d'erreur. (Hérite du global sinon, mais on force la cohérence ici.)

- [ ] **Step 6 : Premier commit — état ALGOR-IT brut**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add -A && git commit -m "Initial commit from ALGOR-IT delivery (2026-06-01) — unchanged"
```
Expected : sortie type `[main (root-commit) <sha>] Initial commit from ALGOR-IT delivery (2026-06-01) — unchanged` avec un nombre élevé de fichiers ajoutés.

**Justification du commit "brut"** : ce premier commit représente l'état exact de la livraison. Toutes nos modifications suivantes seront dans des commits séparés, ce qui rend la traçabilité IP/contractuelle immédiate via `git log --reverse`.

---

## Task 3 : Audit et complétion des `.gitignore`

**Files:**
- Modify: `/Users/hadrienpasset/Developer/batia-webapp/.gitignore`
- Modify: `/Users/hadrienpasset/Developer/batia-webapp/backend/.gitignore`
- Modify: `/Users/hadrienpasset/Developer/batia-webapp/frontend/.gitignore`

**Contexte connu** (extrait de l'audit préalable) :
- Root `.gitignore` couvre `.idea`, `.vscode/settings.json`, `data/database/`, `*.pem`, `devcontainer/.env`, `deploy/configs/*`, `dbhub.toml`
- Backend `.gitignore` couvre `.env.local`, `.env.*.local`, `/vendor/`, `/var/`, `/public/bundles/`, JWT keys
- Frontend `.gitignore` couvre `node_modules`, `dist`, `.env.local`, `.env.*.local`, `/coverage`
- **Aucun ne couvre `.env` "racine" simple** (pattern Symfony : `.env` contient des défauts non sensibles, `.env.local` les overrides sensibles) — c'est volontaire chez Symfony mais on revalidera en Task 4

- [ ] **Step 1 : Vérifier qu'il n'y a pas de fichier sensible déjà tracké**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git ls-files | grep -E '(^|/)(\.env(\.test)?$|\.env\.local|auth\.json|composer\.auth\.json|\.pem$|/jwt/)' | head -20
```
Expected : liste les fichiers sensibles déjà committés au commit 1. Probable : `backend/.env`, `backend/.env.test`, `frontend/.env`. **Noter cette liste pour Task 4**.

- [ ] **Step 2 : Lire les 3 .gitignore en parallèle**

Lire :
- `/Users/hadrienpasset/Developer/batia-webapp/.gitignore`
- `/Users/hadrienpasset/Developer/batia-webapp/backend/.gitignore`
- `/Users/hadrienpasset/Developer/batia-webapp/frontend/.gitignore`

- [ ] **Step 3 : Compléter le `.gitignore` racine avec entrées manquantes**

Ajouter en fin de `/Users/hadrienpasset/Developer/batia-webapp/.gitignore` (utiliser Edit, append-style) :

```gitignore

# Added by batIA — extra coverage
**/.DS_Store
*.swp
*.bak
.history/
coverage/
.phpunit.result.cache
.phpcs-cache
```

Justification : `.DS_Store` (macOS) absents partout ; les autres sont des artefacts de tooling courants non couverts. **Ne pas ajouter `node_modules` ici** : déjà géré par le `.gitignore` frontend.

- [ ] **Step 4 : Commit des compléments gitignore**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add .gitignore && git commit -m "chore(gitignore): add macOS DS_Store, editor swaps, tooling cache patterns"
```
Expected : commit créé avec 1 fichier modifié.

---

## Task 4 : Analyser et sécuriser les fichiers `.env`

**Files:**
- Inspect, modify : `/Users/hadrienpasset/Developer/batia-webapp/backend/.env`
- Inspect, modify : `/Users/hadrienpasset/Developer/batia-webapp/backend/.env.test`
- Inspect, modify : `/Users/hadrienpasset/Developer/batia-webapp/frontend/.env`
- Create : `/Users/hadrienpasset/Developer/batia-webapp/backend/.env.example`
- Create : `/Users/hadrienpasset/Developer/batia-webapp/frontend/.env.example`

**Principe directeur** :
- Convention Symfony : `.env` contient les **défauts non sensibles** et peut/doit être committé. `.env.local` (gitignoré) contient les overrides sensibles.
- Si un `.env` contient déjà des **vraies valeurs sensibles** (tokens, mots de passe, clés API réelles), il faut : (a) extraire ces valeurs dans un `.env.local` non versionné, (b) remplacer la valeur dans `.env` par un placeholder, (c) committer le `.env` désinfecté, (d) créer/mettre à jour un `.env.example`.

- [ ] **Step 1 : Lire les 3 fichiers `.env`**

Lire :
- `/Users/hadrienpasset/Developer/batia-webapp/backend/.env`
- `/Users/hadrienpasset/Developer/batia-webapp/backend/.env.test`
- `/Users/hadrienpasset/Developer/batia-webapp/frontend/.env`

- [ ] **Step 2 : Identifier les variables sensibles**

Pour chaque fichier, lister les variables et catégoriser :
- **Sensible** : `APP_SECRET`, `DATABASE_URL` avec password non-trivial, `JWT_SECRET_KEY`, `JWT_PASSPHRASE`, `MAILER_DSN` avec credentials, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `*_TOKEN`, `*_API_KEY`, `*_PASSWORD`, URL avec `user:password@`
- **Non sensible** : `APP_ENV=dev`, `APP_DEBUG=1`, ports, hostnames `localhost`, URLs publiques, langue, valeurs Symfony par défaut

Reporter le résultat sous forme de tableau dans le commentaire de commit.

- [ ] **Step 3 : Si valeurs sensibles présentes — créer `.env.local` et désinfecter `.env`**

Pour chaque `.env` contenant des sensibles :

a. Créer `<même_dossier>/.env.local` avec les **vraies valeurs** (ce fichier est déjà gitignoré par le `.gitignore` Symfony :  `/.env.local`).

b. Modifier `<dossier>/.env` (utiliser Edit) en remplaçant chaque valeur sensible par un placeholder explicite, ex :
```env
# Avant
APP_SECRET=8f7d6e5c4b3a2918...
# Après
APP_SECRET=__SET_IN_ENV_LOCAL__
```

c. Vérifier que rien d'autre n'a été modifié (juste les valeurs).

**Si aucune valeur sensible** : passer directement au Step 4.

- [ ] **Step 4 : Créer/mettre à jour `.env.example` pour backend et frontend**

`.env.example` = copie de `.env` désinfectée, destinée à être consultée par les nouveaux développeurs.

Run:
```bash
cp /Users/hadrienpasset/Developer/batia-webapp/backend/.env /Users/hadrienpasset/Developer/batia-webapp/backend/.env.example
cp /Users/hadrienpasset/Developer/batia-webapp/frontend/.env /Users/hadrienpasset/Developer/batia-webapp/frontend/.env.example
```

Vérifier (Read) que chaque `.env.example` ne contient AUCUNE valeur sensible. Si oui (par exemple parce que Step 3 a été skippé alors que le fichier en contenait), revenir au Step 3.

- [ ] **Step 5 : Vérification finale anti-fuite**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git diff --cached HEAD -- '**/.env' '**/.env.test' '**/.env.example' 2>&1 | head -100
grep -rIn -E '(password|secret|token|api_?key|aws_access).*=.{8,}' /Users/hadrienpasset/Developer/batia-webapp/backend/.env /Users/hadrienpasset/Developer/batia-webapp/frontend/.env /Users/hadrienpasset/Developer/batia-webapp/backend/.env.test 2>/dev/null | grep -v -E '__SET_IN_ENV_LOCAL__|=__|=\s*$|=changeme|=your_|=example'
```

Expected : la deuxième commande ne ressort RIEN (ou seulement des faux positifs reconnaissables). **Si elle ressort des valeurs réelles** : compléter le Step 3 sur les fichiers concernés.

- [ ] **Step 6 : Commit désinfection**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add backend/.env backend/.env.test backend/.env.example frontend/.env frontend/.env.example && git commit -m "$(cat <<'EOF'
chore(env): sanitize committed .env files, add .env.example

Remplacement des valeurs sensibles dans backend/.env, backend/.env.test
et frontend/.env par des placeholders. Valeurs réelles déplacées vers
backend/.env.local et frontend/.env.local (gitignored).
Ajout de backend/.env.example et frontend/.env.example pour onboarding.
EOF
)"
```

Expected : commit créé. **Si aucun changement n'a été nécessaire** (cas où ALGOR-IT n'avait que des défauts non sensibles), skip ce commit et passer à Task 5.

---

## Task 5 : Documentation de provenance

**Files:**
- Create: `/Users/hadrienpasset/Developer/batia-webapp/docs/provenance/ALGOR-IT-handover.md`
- Create: `/Users/hadrienpasset/Developer/batia-webapp/docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md` (copie)

- [ ] **Step 1 : Créer les dossiers docs**

Run:
```bash
mkdir -p /Users/hadrienpasset/Developer/batia-webapp/docs/provenance
mkdir -p /Users/hadrienpasset/Developer/batia-webapp/docs/superpowers/specs
mkdir -p /Users/hadrienpasset/Developer/batia-webapp/docs/superpowers/plans
mkdir -p /Users/hadrienpasset/Developer/batia-webapp/docs/audit
```

- [ ] **Step 2 : Écrire `docs/provenance/ALGOR-IT-handover.md`**

Créer le fichier avec ce contenu exact :

```markdown
# Provenance de la livraison

## Origine

**Société** : ALGOR-IT (gitlab.com/algoritca)
**Repo source** : `gitlab.com:algoritca/select-batia/webapp.git` (privé, plus utilisé par batIA)
**Date de réception** : 2026-06-01
**Format reçu** : archive ZIP extraite (`~/Downloads/webapp-main/`)
**Historique git** : NON inclus dans la livraison (snapshot sans `.git/`)

## Statut IP

**Cession pleine propriété** à batIA. batIA peut librement modifier, redistribuer en interne, intégrer dans son produit. Le composer.json mentionne encore `"license": "proprietary"` côté ALGOR-IT — sera mis à jour ultérieurement.

## Snapshot byte-exact préservé

Une copie figée et read-only du livrable est conservée hors-Git à :
`/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`

Cette copie sert de preuve contractuelle de l'état exact de la livraison. Ne jamais la modifier.

## Stack livrée (résumé)

- **Backend** : Symfony 7.3, PHP ≥8.2, Doctrine ORM 3, JWT, Flysystem S3, Messenger AMQP, WebSocket
- **Frontend** : React 18 + TypeScript + Vite, Chakra UI 2, TanStack Query, Storybook, Vitest
- **Infra dev** : Docker + MySQL, registre Docker `registry.gitlab.com` (privé ALGOR-IT)
- **Bundles propriétaires AICLIB** : `aiclib/core-bundle ^1.0`, `aiclib/user-bundle ^1.0` (à auditer pour vérifier accès au source)
- **Migrations Doctrine** : 114 fichiers

## Contact ALGOR-IT

À compléter : nom du chef de projet, email, conditions de support post-livraison.

## Documents associés

- Spec d'onboarding : `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md`
- Rapport d'audit (à venir) : `docs/audit/AUDIT.md`
- Procédure boot local (à venir) : `docs/provenance/local-boot-procedure.md`
```

- [ ] **Step 3 : Copier le spec depuis `planRoomRecognition`**

Run:
```bash
cp /Users/hadrienpasset/Developer/planRoomRecognition/docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md /Users/hadrienpasset/Developer/batia-webapp/docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md
```

- [ ] **Step 4 : Copier également le plan courant** (ce fichier)

Run:
```bash
cp /Users/hadrienpasset/Developer/planRoomRecognition/docs/superpowers/plans/2026-06-03-batia-webapp-bootstrap.md /Users/hadrienpasset/Developer/batia-webapp/docs/superpowers/plans/2026-06-03-batia-webapp-bootstrap.md
```

- [ ] **Step 5 : Commit documentation de provenance**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add docs/ && git commit -m "docs(provenance): add ALGOR-IT handover, onboarding spec, bootstrap plan"
```

Expected : commit créé avec ~3-4 fichiers ajoutés.

---

## Task 6 : `CLAUDE.md` d'amorçage à la racine

**Files:**
- Create: `/Users/hadrienpasset/Developer/batia-webapp/CLAUDE.md`

- [ ] **Step 1 : Écrire `CLAUDE.md`**

Créer `/Users/hadrienpasset/Developer/batia-webapp/CLAUDE.md` avec ce contenu :

```markdown
# CLAUDE.md — batia-webapp

> Fichier d'amorçage pour Claude Code. Lis-moi en premier dans toute nouvelle conversation sur ce repo.

## Identité du projet

`batia-webapp` est la **webapp principale de batIA** (SaaS B2B pour électriciens). Stack Symfony 7.3 + React 18.

batIA est porté par Hadrien Passet (CTO fondateur, solo, hadrien.passet@gmail.com). Le produit utilise une pipeline IA pour analyser les plans d'électricité et générer des devis. La webapp est le point d'entrée artisan.

## Provenance (IMPORTANT)

Ce code a été livré par la société ALGOR-IT le **2026-06-01**, sous cession pleine propriété à batIA. Détails dans `docs/provenance/ALGOR-IT-handover.md`.

Un snapshot byte-exact de la livraison est conservé read-only à :
`/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`
**Ne jamais modifier ce snapshot.**

## Architecture multi-repo

- `~/Developer/planRoomRecognition/` : services Python ML (YOLO, segmentation pièces, pastilles, tableau électrique)
- `~/Developer/batia-webapp/` (ICI) : Symfony + React, point d'entrée artisan, qui devra appeler les services Python
- L'intégration ML ↔ webapp est **à concevoir** (Phase 4 — cycle brainstorming séparé)

## Phase courante

Voir `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md` pour le plan global.

État au moment de la rédaction de ce fichier : Phase 1 terminée (bootstrap). Prochaines phases : Phase 2 audit complet (7 axes, livrable `docs/audit/AUDIT.md`), Phase 3 boot local Docker.

## Stack

- **Backend** : Symfony 7.3, PHP ≥8.2, Doctrine ORM 3, JWT (Lexik + refresh), Flysystem S3, Messenger AMQP, WebSocket. Bundles propriétaires `aiclib/core-bundle`, `aiclib/user-bundle`.
- **Frontend** : React 18 + TypeScript + Vite, Chakra UI 2, dnd-kit, TanStack Query/Table, react-hook-form, i18next, react-router 6, Storybook 8, Vitest, Tailwind.
- **Infra dev** : Docker (`make build-devcontainer && make up`), MySQL, images sur `registry.gitlab.com` (privé ALGOR-IT, token requis).

## Règles de manipulation

- **Préserver les copyrights ALGOR-IT** dans les en-têtes de fichiers source originaux (légalement la cession est faite mais on ne réécrit pas l'historique d'auteur sans raison).
- **Commits atomiques et descriptifs** : ne pas mélanger sécurisation env, ajout features, et formatage.
- **Tests AVANT modification de logique métier** : la base ALGOR-IT a PHPUnit + Vitest configurés, les exploiter.
- **Ne jamais committer de secrets** : `.env.local` (gitignoré) pour valeurs sensibles, `.env` pour défauts non sensibles, `.env.example` à jour pour onboarding.

## Fichiers clés à connaître

- `composer.json`, `package.json` — dépendances
- `backend/src/` — code Symfony
- `frontend/src/` — code React
- `backend/config/` — config Symfony (security, services, bundles)
- `backend/migrations/` — 114 migrations Doctrine
- `database.dbml` — schéma de la BDD
- `documentation/` — doc rédigée par ALGOR-IT (backend, frontend, websocket, déploiement, db)
- `AGENTS.md` (back+front) — conventions de travail avec agents IA (équivalent CLAUDE.md, multi-vendor)
- `Makefile` — commandes principales (`make up`, `make down`, `make build-devcontainer`, `make test`)

## Conventions de commit

Format conventionnel : `<type>(<scope>): <description>` (ex : `feat(auth): add password reset`, `fix(devis): handle empty rooms`, `chore(deps): bump symfony to 7.3.1`).

Types : `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`, `style`, `ci`.

## Liens utiles

- Repo GitHub : https://github.com/HPasset/batia-webapp
- Spec onboarding : `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md`
- Provenance : `docs/provenance/ALGOR-IT-handover.md`
```

- [ ] **Step 2 : Commit CLAUDE.md**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add CLAUDE.md && git commit -m "docs(claude): add CLAUDE.md amorçage for future conversations"
```

---

## Task 7 : Remplacer la LICENSE par celle de batIA

**Files:**
- Create or replace: `/Users/hadrienpasset/Developer/batia-webapp/LICENSE`

- [ ] **Step 1 : Vérifier si une LICENSE existe déjà**

Run:
```bash
ls /Users/hadrienpasset/Developer/batia-webapp/LICENSE* 2>&1
```
Expected : soit `No such file or directory` (pas de LICENSE), soit un fichier existant.

- [ ] **Step 2 : Écrire la nouvelle LICENSE**

Créer (ou écraser) `/Users/hadrienpasset/Developer/batia-webapp/LICENSE` :

```
Copyright (c) 2026 batIA (Hadrien Passet)

Tous droits réservés.

Ce logiciel et le code source associé sont la propriété exclusive de batIA,
suite à cession pleine propriété par ALGOR-IT en date du 2026-06-01.

Aucune partie de ce logiciel ne peut être reproduite, distribuée ou utilisée
hors du périmètre interne de batIA et de ses prestataires autorisés sans
accord écrit préalable.

Le code source contient des éléments initialement développés par ALGOR-IT,
dont les copyrights d'auteur originaux sont préservés dans les en-têtes
des fichiers source concernés. La cession des droits d'exploitation est
toutefois pleine et entière au bénéfice de batIA.
```

- [ ] **Step 3 : Commit LICENSE**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add LICENSE && git commit -m "chore(license): set batIA proprietary license (post ALGOR-IT IP transfer)"
```

---

## Task 8 : Réécrire `README.md` pour le contexte batIA

**Files:**
- Modify: `/Users/hadrienpasset/Developer/batia-webapp/README.md`

- [ ] **Step 1 : Lire le README actuel**

Lire `/Users/hadrienpasset/Developer/batia-webapp/README.md` pour mémoire (référence rapide à ses sections utiles : URL clone, démarrage Docker, restore dump SQL).

- [ ] **Step 2 : Écrire le nouveau README**

Écraser `/Users/hadrienpasset/Developer/batia-webapp/README.md` avec :

```markdown
# batia-webapp

Webapp principale de **batIA** — SaaS B2B pour électriciens artisans.

Stack : **Symfony 7.3** (backend) + **React 18 + TypeScript + Vite** (frontend), packagé en environnement de dev Docker.

> Code initialement livré par **ALGOR-IT** le 2026-06-01 sous cession pleine propriété. Voir [`docs/provenance/ALGOR-IT-handover.md`](docs/provenance/ALGOR-IT-handover.md).

## Première installation

### Prérequis

- macOS / Linux (testé macOS 15)
- Docker Desktop 4.x ou Docker Engine 24+
- `make`
- `gh` CLI (pour interactions GitHub)
- Token d'accès `registry.gitlab.com` (les images dev sont sur le registre privé ALGOR-IT — à demander si non fourni)

### Setup

1. Cloner :
   ```bash
   gh repo clone HPasset/batia-webapp
   cd batia-webapp
   ```

2. Configurer les secrets locaux :
   ```bash
   cp backend/.env.example backend/.env.local
   cp frontend/.env.example frontend/.env.local
   # éditer les fichiers .env.local pour y mettre les vraies valeurs
   ```

3. Login registre Docker :
   ```bash
   echo "$GITLAB_TOKEN" | docker login registry.gitlab.com -u <nom_token> --password-stdin
   ```

4. Build & démarrage :
   ```bash
   make build-devcontainer
   make up
   ```

5. Restorer un dump local (si fourni) :
   ```bash
   docker exec -i batia-webapp-database mysql -uroot -ptiger api < data/database/<dump>.sql
   ```

## Commandes utiles

| Commande | Effet |
|----------|-------|
| `make up` | Démarre tous les conteneurs |
| `make down` | Arrête tous les conteneurs |
| `make build-devcontainer` | Reconstruit les images dev |
| `make test` | Lance les tests |
| `docker logs <container> -f` | Suit les logs d'un conteneur |

Liste complète : voir `Makefile`.

## Structure

```
backend/      → Symfony 7.3 API
frontend/     → React + Vite app
devcontainer/ → docker-compose.yml + Dockerfiles
documentation/ → doc rédigée par ALGOR-IT
data/         → dumps SQL, fixtures
docs/         → doc batIA (audit, provenance, specs)
```

## Documentation

- [Provenance de la livraison](docs/provenance/ALGOR-IT-handover.md)
- [Spec d'onboarding (batIA)](docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md)
- [Audit complet](docs/audit/AUDIT.md) *(à venir — Phase 2)*
- [Documentation backend (ALGOR-IT)](documentation/backend-configuration.md)
- [Documentation frontend (ALGOR-IT)](documentation/frontend-configuration.md)
- [Système d'envoi d'emails](documentation/email-system.md)
- [Configuration BDD](documentation/database/configuration.md)
- [Déploiement](documentation/deploy-configuration.md)
- [Serveur websocket](documentation/websocket.md)

## En cas de problèmes

### Glitchtip
S'il est configuré : https://logs.algor-it-conseils.ca/algor-it/issues (legacy, à migrer)

### Logs
```bash
docker logs <container> -f
# ou pour tous les logs en mode foreground :
make down
docker compose -f devcontainer/docker-compose.yml up
```

## Licence

Voir [`LICENSE`](LICENSE). Propriété de batIA suite à cession ALGOR-IT.

---

Copyright © 2026 batIA. Tous droits réservés.
```

- [ ] **Step 3 : Vérifier que les liens vers `documentation/*` existent**

Run:
```bash
ls /Users/hadrienpasset/Developer/batia-webapp/documentation/ 2>&1
```
Expected : les sous-fichiers référencés dans le nouveau README existent (`backend-configuration.md`, `frontend-configuration.md`, `email-system.md`, `database/`, etc.). **Si un fichier référencé manque** : retirer le lien correspondant du README.

- [ ] **Step 4 : Commit README**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git add README.md && git commit -m "docs(readme): rewrite README for batIA context, link to provenance and audit"
```

---

## Task 9 : Bootstrap memory Claude pour `batia-webapp`

**Files:**
- Create: `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/MEMORY.md`
- Create: `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/user_profile.md`
- Create: `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/project_batia_webapp.md`
- Create: `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/project_algor_it_provenance.md`
- Create: `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/reference_planroom_repo.md`

**Note** : ces fichiers sont écrits HORS du repo Git. Pas de commit.

- [ ] **Step 1 : Créer le dossier memory**

Run:
```bash
mkdir -p /Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory
```

- [ ] **Step 2 : Écrire `user_profile.md`**

Créer `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/user_profile.md` :

```markdown
---
name: user-profile
description: Hadrien Passet, CTO fondateur solo batIA, MacBook M5 Pro, Python pyenv 3.11.11, ML/YOLO/fullstack
metadata:
  type: user
---

Hadrien Passet, CTO fondateur **solo** de batIA (SaaS B2B électriciens, beta avril 2026).
- Email : hadrien.passet@gmail.com
- Setup : MacBook M5 Pro, pyenv 3.11.11
- Compétences : ML (YOLO, segmentation), fullstack, prend les décisions techniques seul
- Communication : français, direct, attend des recommandations expertes et pas de questions évidentes
- Préfère un journal de bord quotidien dans `docs/journal/YYYY-MM-DD.md` sur les autres projets — peut être à activer ici aussi

Voir aussi [[project-batia-webapp]] pour le contexte projet courant.
```

- [ ] **Step 3 : Écrire `project_batia_webapp.md`**

Créer `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/project_batia_webapp.md` :

```markdown
---
name: project-batia-webapp
description: batia-webapp = Symfony 7.3 + React 18 livré par ALGOR-IT 2026-06-01, en cours d'onboarding (audit + intégration ML à venir)
metadata:
  type: project
---

# batia-webapp

Webapp principale batIA — point d'entrée artisan électricien. Stack Symfony 7.3 + React 18 + TS + Vite + Chakra 2.

## Origine et statut IP

Code livré par ALGOR-IT (gitlab.com/algoritca) le **2026-06-01** sous **cession pleine propriété** à batIA. Snapshot byte-exact préservé read-only à `/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/`. Voir [[project-algor-it-provenance]].

## Phase courante (mise à jour 2026-06-03)

Phase 1 (bootstrap repo) terminée. **Prochaines étapes** :
- Phase 2 : audit complet 7 axes → `docs/audit/AUDIT.md`
- Phase 3 : boot local Docker → `docs/provenance/local-boot-procedure.md`
- Phase 4 : design intégration ML avec [[reference-planroom-repo]] (cycle brainstorming séparé)

## Spec de référence

`docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md` — à lire au démarrage de chaque conversation pour comprendre où on en est.

## Stack technique

- **Backend** : Symfony 7.3, PHP ≥8.2, Doctrine ORM 3, JWT (Lexik), Flysystem S3, Messenger AMQP, WebSocket
- **Bundles propriétaires AICLIB** (ALGOR-IT) : `aiclib/core-bundle`, `aiclib/user-bundle` — accès au source à vérifier en Phase 2
- **Frontend** : React 18, TS, Vite, Chakra UI 2, TanStack Query/Table, Storybook 8, Vitest
- **Infra dev** : Docker + MySQL, registre `registry.gitlab.com` privé (token requis)
- **114 migrations Doctrine** côté DB

## Règles spécifiques

- Préserver les copyrights ALGOR-IT dans les en-têtes des fichiers source originaux
- Ne JAMAIS toucher le snapshot vendor read-only
- Commits atomiques, conventionnels (`feat(scope): ...`)
- `.env.local` pour secrets, `.env` pour défauts, `.env.example` à jour

## Repo GitHub

https://github.com/HPasset/batia-webapp (privé)
```

- [ ] **Step 4 : Écrire `project_algor_it_provenance.md`**

Créer `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/project_algor_it_provenance.md` :

```markdown
---
name: project-algor-it-provenance
description: Livraison ALGOR-IT 2026-06-01, cession pleine propriété, snapshot préservé read-only
metadata:
  type: project
---

# Provenance livraison ALGOR-IT

**Société** : ALGOR-IT (gitlab.com/algoritca)
**Repo source d'origine** : `gitlab.com:algoritca/select-batia/webapp.git`
**Date livraison** : 2026-06-01
**Format reçu** : archive ZIP extraite (sans `.git/`, donc pas d'historique)
**Statut IP** : cession pleine propriété à batIA

**Why** : ALGOR-IT a conçu la première brique de batIA en prestation. batIA continue maintenant en interne. La cession permet librement de modifier, étendre, intégrer la pipeline ML maison.

**How to apply** :
- Le snapshot read-only à `/Users/hadrienpasset/Developer/batia-vendor-deliverables/algor-it-2026-06-01/` est une **preuve contractuelle**, jamais modifier
- Les bundles `aiclib/*` (Composer) sont propriétaires ALGOR-IT — accès au source à vérifier (risque bloquant si bug)
- Le registre Docker `registry.gitlab.com` est privé ALGOR-IT — dépendance à migrer vers GHCR à terme
- Contact ALGOR-IT à compléter dans `docs/provenance/ALGOR-IT-handover.md`

Voir [[project-batia-webapp]] pour l'état projet courant.
```

- [ ] **Step 5 : Écrire `reference_planroom_repo.md`**

Créer `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/reference_planroom_repo.md` :

```markdown
---
name: reference-planroom-repo
description: Repo soeur ~/Developer/planRoomRecognition contient les services Python ML à intégrer en Phase 4
metadata:
  type: reference
---

Le repo **`~/Developer/planRoomRecognition/`** contient les briques Python ML qui devront s'intégrer à `batia-webapp` en Phase 4 :
- YOLO détection équipements (v3 mAP50=0.92, v4 instable)
- Segmentation pièces (Mask2Former Swin-S, 10 classes, MVP sur branche `feat/segmentation-mvp`)
- Pastilles canvas (custom Streamlit component React/TS)
- Tableau électrique (NFC C 15-100, rendu SVG)

GitHub : https://github.com/HPasset/planRoomRecognition

Les specs et plans antérieurs sont dans `planRoomRecognition/docs/superpowers/specs/` et `planRoomRecognition/docs/superpowers/plans/`. Le spec d'onboarding actuel de `batia-webapp` y a été écrit en premier (2026-06-03) puis dupliqué ici lors du bootstrap.

L'intégration côté webapp se fera probablement via :
- microservice HTTP/REST (FastAPI) appelé par Symfony, OU
- worker async via AMQP (Symfony Messenger déjà en place côté ALGOR-IT)

Choix à acter en Phase 4 après audit (Phase 2).
```

- [ ] **Step 6 : Écrire `MEMORY.md` index**

Créer `/Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/MEMORY.md` :

```markdown
# Memory Index

| File | Description |
|------|-------------|
| `user_profile.md` | Hadrien Passet, CTO fondateur solo batIA, MacBook M5 Pro, Python pyenv 3.11.11, ML/YOLO/fullstack |
| `project_batia_webapp.md` | batia-webapp = Symfony 7.3 + React 18 livré par ALGOR-IT 2026-06-01, en cours d'onboarding |
| `project_algor_it_provenance.md` | Livraison ALGOR-IT 2026-06-01, cession pleine propriété, snapshot préservé read-only |
| `reference_planroom_repo.md` | Repo soeur ~/Developer/planRoomRecognition contient les services Python ML à intégrer en Phase 4 |
```

- [ ] **Step 7 : Vérifier que le memory est bien écrit**

Run:
```bash
ls -la /Users/hadrienpasset/.claude/projects/-Users-hadrienpasset-Developer-batia-webapp/memory/
```
Expected : 5 fichiers listés (MEMORY.md + 4 fichiers de mémoire).

---

## Task 10 : Créer le repo GitHub privé et pousser

**Files:**
- Remote: `github.com/HPasset/batia-webapp` (privé)

- [ ] **Step 1 : Vérifier `gh` CLI authentifié**

Run:
```bash
gh auth status
```
Expected : `Logged in to github.com as HPasset` (ou similaire). **Si non authentifié** : `gh auth login` interactif (à faire manuellement).

- [ ] **Step 2 : Vérifier qu'un repo `HPasset/batia-webapp` n'existe pas déjà**

Run:
```bash
gh repo view HPasset/batia-webapp 2>&1 | head -5 || echo "REPO_DOES_NOT_EXIST_OK"
```
Expected : `REPO_DOES_NOT_EXIST_OK` (le `||` se déclenche sur erreur).

- [ ] **Step 3 : Créer le repo privé sur GitHub**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && gh repo create HPasset/batia-webapp --private --description "batIA webapp — Symfony 7.3 + React 18 (livraison ALGOR-IT 2026-06-01, cession pleine propriété)" --source=. --remote=origin
```
Expected : sortie type `✓ Created repository HPasset/batia-webapp on GitHub` puis `✓ Added remote https://github.com/HPasset/batia-webapp.git`.

- [ ] **Step 4 : Vérifier le remote configuré**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git remote -v
```
Expected :
```
origin	https://github.com/HPasset/batia-webapp.git (fetch)
origin	https://github.com/HPasset/batia-webapp.git (push)
```

- [ ] **Step 5 : Pousser `main`**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git push -u origin main
```
Expected : sortie de push réussie, branche `main` trackée. Tous les commits visibles.

- [ ] **Step 6 : Vérifier sur GitHub**

Run:
```bash
gh repo view HPasset/batia-webapp --json visibility,defaultBranchRef,pushedAt
```
Expected : `"visibility":"PRIVATE"`, `"defaultBranchRef":{"name":"main"}`, `"pushedAt"` récent.

- [ ] **Step 7 : Vérifier visuellement sur l'interface web**

Run:
```bash
gh repo view HPasset/batia-webapp --web
```
Effet : ouvre le navigateur sur le repo. Vérifier que :
- README batIA s'affiche bien
- LICENSE visible
- Structure correcte (backend/, frontend/, docs/, …)

- [ ] **Step 8 : Vérifier l'historique des commits**

Run:
```bash
cd /Users/hadrienpasset/Developer/batia-webapp && git log --oneline
```
Expected : 6-8 commits, dans l'ordre (du plus récent au plus ancien) :
1. `docs(readme): rewrite README for batIA context…`
2. `chore(license): set batIA proprietary license…`
3. `docs(claude): add CLAUDE.md amorçage…`
4. `docs(provenance): add ALGOR-IT handover, onboarding spec, bootstrap plan`
5. `chore(env): sanitize committed .env files, add .env.example` *(optionnel)*
6. `chore(gitignore): add macOS DS_Store, editor swaps, tooling cache patterns`
7. `Initial commit from ALGOR-IT delivery (2026-06-01) — unchanged`

---

## Critères d'acceptation globaux du Plan A

- [ ] Snapshot vendor read-only existe et est intouchable
- [ ] Repo `~/Developer/batia-webapp/` initialisé, premier commit = livraison ALGOR-IT brute
- [ ] Aucun secret committé (vérifié par grep en Task 4 Step 5)
- [ ] `.env.example` présents et utilisables pour onboarding
- [ ] `CLAUDE.md` racine permet à un Claude amnésique de reprendre le projet
- [ ] LICENSE batIA en place
- [ ] README contextualisé batIA, liens valides
- [ ] Memory bootstrap écrit dans le bon path Claude
- [ ] Repo GitHub privé créé, `main` poussée
- [ ] `git log` montre des commits atomiques et descriptifs

## Sortie attendue

Un repo GitHub privé `HPasset/batia-webapp` à l'état exact pour démarrer la Phase 2 (audit).

## Suite

À l'issue de ce plan : écrire **Plan B — Audit complet** (`docs/superpowers/plans/<date>-batia-webapp-audit.md`) dans le contexte du nouveau dossier `batia-webapp/`. Le démarrer en nouvelle conversation Claude avec en premier prompt :
> « Lis `CLAUDE.md` puis `docs/superpowers/specs/2026-06-03-batia-webapp-onboarding-design.md`. On démarre la Phase 2 audit. »
