# Avancement segmentation des pièces — Stage A
## Présentation board batIA — 11 mai 2026

---

## Slide 1 — Couverture

**Titre :** Avancement technique — Brique B (segmentation des pièces)

**Sous-titre :** Stage A : pré-entraînement sur dataset open source CubiCasa5K

**Date :** 11 mai 2026

**Auteur :** Hadrien Passet — CTO

**Notes présentateur :** Rappel que cette brique est la "colonne vertébrale" du pipeline IA batIA — sans polygones de pièces, l'application des règles NFC est impossible.

---

## Slide 2 — Le rôle de la brique segmentation dans batIA

**Titre :** Pourquoi cette brique est critique

**Contenu :**

- Le pipeline batIA prend en entrée un plan d'étage et produit en sortie un devis électrique
- **La brique segmentation détecte chaque pièce et son type** (cuisine, chambre, sdb...)
- Sans cette information, impossible d'appliquer les règles NF C 15-100 par pièce :
  - Cuisine → 6 prises 16A minimum + prise spécialisée 32A
  - Salle de bain → restrictions de volumes (zones interdites prises)
  - Chambre → interrupteurs va-et-vient au chevet du lit
- C'est **la brique la plus importante en amont** du moteur de règles NFC

**Notes :** Insister que ce n'est pas juste de la détection mais de la géométrie précise (polygones, pas rectangles) — nécessaire pour calcul de surface, placement composants.

---

## Slide 3 — Choix d'architecture : Mask2Former

**Titre :** Modèle choisi : Mask2Former (Meta AI)

**Contenu :**

- **Mask2Former** = état de l'art segmentation panoptique (publication Meta AI 2022)
- **Différence vs YOLO** :
  - YOLO = rectangles autour des objets (où est le canapé ?)
  - Mask2Former = contour exact des pièces (où sont les murs de la cuisine ?)
- **Pré-entraîné sur COCO** (133 classes, 200K images) → on bénéficie de ses capacités générales
- **Fine-tuné** sur les plans d'étage pour notre tâche spécifique
- Architecture : 50M paramètres, transformer Swin-Small backbone

**Schéma à dessiner :** un plan en entrée → flèche → image avec polygones colorés par type de pièce

**Notes :** Vulgarisation : c'est comme un coloriage automatique où chaque pièce reçoit sa couleur correspondant à son type.

---

## Slide 4 — Taxonomie des classes (10 classes finales)

**Titre :** 10 types de pièces détectés

**Tableau :**

| ID | Classe | Rôle |
|---|---|---|
| 0 | Background | Extérieur du bâtiment |
| 1 | Wall | Murs porteurs + cloisons |
| 2 | Kitchen | Cuisine |
| 3 | LivingRoom | Séjour / salon / dining |
| 4 | BedRoom | Chambre |
| 5 | Bath | Salle de bain + WC |
| 6 | Entry | Entrée + couloir |
| 7 | Storage | Rangement, dressing, buanderie |
| 8 | Garage | Garage |
| 9 | Outdoor | Balcon, terrasse |

**Notes :** Choix taxonomique aligné NFC : on garde uniquement les distinctions qui changent les règles électriques. Ex: WC fusionné avec Bath (mêmes règles).

---

## Slide 5 — Dataset d'entraînement : CubiCasa5K

**Titre :** Dataset CubiCasa5K — 4 745 plans d'étage annotés

**Contenu :**

- Dataset open source d'origine finlandaise (Aalto University)
- 5 000 plans architecturaux 2D au format SVG
- Annotations polygones de pièces + meubles + structure
- Splits : 4 000 train / 467 val / 479 test
- 10 GB de données, exporté en format panoptic prêt pour entraînement

**Visuel suggéré :** screenshot d'un plan CubiCasa avec pièces colorées (tu peux générer en lançant `eval_visualize.py` après training)

**Notes :** Dataset gratuit + licence permissive permettant usage commercial. Limité au style finlandais → d'où le besoin du Stage B sur plans FR.

---

## Slide 6 — Résultats Stage A — Évolution loss & mIoU

**Titre :** 4 jours de training sur Mac M5 Pro

**Métriques globales :**

- **Loss training** : 95 → 30 (descente régulière, validée sur 4 j de training)
- **mIoU validation** : 0.135 (epoch 1) → **0.51 (epoch 55, en cours)**
- Cible MVP : mIoU ≥ 0.55 (atteignable d'ici epoch 70-80)
- Modèle stable, aucune divergence depuis les correctifs

**Visuel suggéré :** screenshot W&B des courbes train/loss + val/mIoU

**Notes :** mIoU = "mean Intersection over Union" — métrique standard segmentation. 1.0 = parfait, 0 = tout faux. 0.5+ = bon résultat industriel sur ce type de tâche.

---

## Slide 7 — Résultats par classe (epoch 55)

**Titre :** Performance par type de pièce

**Tableau :**

| Classe | IoU | Lecture |
|---|---|---|
| Background | **0.83** | ✅ Excellent |
| BedRoom | **0.60** | ✅ Excellent |
| LivingRoom | **0.60** | ✅ Excellent |
| Kitchen | **0.60** | ✅ Excellent |
| Outdoor | 0.54 | ✅ Bon |
| Entry | 0.48 | ⚠ Correct |
| Bath | 0.46 | ⚠ Correct |
| Garage | 0.46 | ⚠ Correct (rare) |
| Storage | 0.35 | ⚠ Modeste (classe hétérogène) |
| Wall | 0.26 | ⚠ Difficile (lignes fines) |

**Notes :** Les 4 classes principales pour batIA (Cuisine, Chambre, Séjour, SDB en approche) sont au-dessus de 0.45-0.60 → utilisable en prod. Wall et Storage sont structurellement plus durs mais ne bloquent pas le pipeline.

---

## Slide 8 — Difficultés rencontrées et résolues

**Titre :** Itérations techniques (transparence)

**Bullet points :**

- **Bug 1 — Mapping CubiCasa erroné** : la classe "Bedroom" du dataset (la plus fréquente !) n'était pas reconnue → corrigée par audit complet des labels
- **Bug 2 — Background non entraîné** : architecturalement, la classe 0 n'apparaissait pas comme cible → mIoU plafonnait à 9/10 du potentiel. Corrigé.
- **Bug 3 — NaN loss** : précision BF16 sur Mac MPS provoquait des explosions numériques → migration FP32 (un peu plus lent mais stable)
- **Bug 4 — MPS missing op** : opération `grid_sampler_2d_backward` non implémentée sur MPS → fallback CPU activé
- **Optimisation thermique** : training nocturne ralenti par sleep macOS → utilisation `caffeinate` pour empêcher le sleep

**Notes :** Démontre la rigueur du process. Chaque bug détecté a été investigué, corrigé, validé par tests. Aucun "ça marche ¯\\_(ツ)_/¯".

---

## Slide 9 — Limite actuelle : domain gap CubiCasa ↔ FR

**Titre :** Pourquoi un Stage B est nécessaire

**Contenu :**

- Le modèle est entraîné sur des **plans finlandais** (CubiCasa)
- Les **plans FR ont des conventions visuelles différentes** :
  - Symboles de meubles distincts (lavabo, baignoire, lit dessinés autrement)
  - Cotations partout en mètres (CubiCasa n'en a pas)
  - Légendes, hachures de murs spécifiques
- Sans adaptation, le modèle galère sur les plans clients réels
- → Solution : **fine-tuning sur ~150 plans FR annotés à la main**

**Visuel suggéré :** comparaison côte-à-côte d'un plan CubiCasa vs un plan FR typique

**Notes :** Ce Stage B est un investissement humain (15-25h d'annotation) nécessaire pour la robustesse production. Pas un re-training from scratch — on garde tout ce qu'on a appris.

---

## Slide 10 — Stage B : roadmap fine-tuning FR

**Titre :** Prochaine étape : Stage B (3-4 semaines)

**Phases :**

1. **Collecte plans FR** (en cours, ~150 plans cible)
   - Sources : contacts électriciens, data.gouv.fr, plans perso
2. **Annotation manuelle** (~15-25h étalées sur 2 semaines)
   - Outil : CVAT (open-source, gratuit, hébergé localement)
   - Pré-annotation automatique par modèle Stage A → on corrige uniquement
3. **Fine-tuning** (~24-48h calcul)
   - Modèle Stage A + plans FR pondérés
   - LR 10× plus bas pour adaptation subtile
4. **Évaluation finale** sur 50 plans FR "gold" (jamais touchés au training)
   - Cible : mIoU ≥ 0.55 sur plans FR

**Notes :** Pendant l'annotation, je peux préparer en parallèle le YOLO meubles (brique A) et débuter le travail sur l'OCR.

---

## Slide 11 — Vue d'ensemble du pipeline batIA complet

**Titre :** Architecture multi-briques du pipeline IA

**Schéma :**

```
Plan d'étage en entrée
       ↓
┌──────────────────────────────────────────┐
│  Brique B : Mask2Former (segmentation)    │ ← actuellement
│  → polygones de pièces typées            │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  Brique A : YOLO (détection meubles)     │ ← v3 OK doors/windows
│  → bbox lits, sanitaires, cuisine        │   refonte 10 classes prévue
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  OCR (lecture des labels écrits)          │ ← prochaine brique
│  → confirme types de pièces              │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  Moteur de règles NFC C 15-100           │ ← code applicatif
│  → placement prises + interrupteurs      │
└──────────────────────────────────────────┘
       ↓
   Plan annoté + devis automatique
```

**Notes :** Chaque brique compense les faiblesses des autres. Mask2Former donne la géométrie, YOLO les meubles, OCR confirme les types, le moteur NFC applique les règles. C'est cette architecture qui garantit la robustesse.

---

## Slide 12 — Calendrier prévisionnel jusqu'à beta

**Titre :** Roadmap MVP — objectifs & jalons

**Timeline :**

| Période | Livrable |
|---|---|
| **mi-mai** | Stage A terminé, modèle CubiCasa baseline |
| **fin mai** | Annotation FR commencée, YOLO meubles refait sur 10 classes |
| **mi-juin** | Stage B fine-tune FR terminé, mIoU ≥ 0.55 atteint |
| **fin juin** | Brique OCR opérationnelle |
| **juillet** | Intégration moteur NFC + UX MVP |
| **août** | Tests internes sur cas d'usage réels |
| **sept-oct** | Pilotes utilisateurs (3-5 électriciens) |
| **avril 2026** | **Beta production** ✓ |

**Notes :** Calendrier conservateur. Si les itérations Stage B sont plus rapides que prévu, on peut accélérer le pilote.

---

## Slide 13 — État technique global

**Titre :** Synthèse santé du projet

**Indicateurs :**

| Indicateur | État | Commentaire |
|---|---|---|
| Architecture pipeline | ✅ Validée | 5 briques, design éprouvé |
| Brique B (segmentation) | 🟡 Stage A 70% | mIoU 0.51 → cible 0.55 |
| Brique A (YOLO objets) | 🟡 v3 OK doors/windows | Refonte 10 classes prévue |
| OCR | ⚪ À démarrer | Non bloquant pour Stage B |
| Moteur NFC | ⚪ À écrire | Code applicatif post-IA |
| Dataset CubiCasa | ✅ Complet | 4 745 plans exportés |
| Dataset FR | 🔴 0 plans | Action principale à venir |
| Infrastructure code | ✅ Stable | 50+ tests automatisés |

**Notes :** Le risque #1 est la collecte de plans FR. Action : je vais activer mes contacts cette semaine. Tout le reste est sous contrôle.

---

## Slide 14 — Conclusion + questions

**Titre :** À retenir

**Bullet points :**

- **Stage A en finition** : modèle CubiCasa atteindra son palier sous 24-48h
- **Tous les bugs majeurs corrigés** : training stable, métrique en croissance régulière
- **Pipeline complet design validé** : 5 briques, architecture multi-modèles
- **Prochain jalon majeur** : collecte 150 plans FR + annotation (3-4 semaines)
- **Risque principal identifié** : qualité du dataset FR — gérable via réseau électriciens
- **Beta avril 2026 reste atteignable**

**Closing :** Questions ?

---

## Notes générales pour l'orateur

**Durée cible** : 15-20 min de présentation + 10 min Q&A

**Points à insister** :
1. La rigueur du process : audit, debug, tests automatisés (≠ "je bricole")
2. La modularité du pipeline : chaque brique a un rôle clair, on peut les itérer indépendamment
3. Le risque humain (collecte FR) est identifié et a une solution

**Questions possibles à anticiper** :
- "Pourquoi pas du cloud GPU pour aller plus vite ?" → coût, contrôle, données privées clients
- "Combien de temps Stage B ?" → 3-4 semaines incluant collecte + annotation + training
- "Le modèle marche-t-il sur des plans manuscrits ?" → pas testé encore, à valider au domain test
- "Combien ça nous coûte aujourd'hui ?" → quasi 0 € (Mac perso, datasets gratuits, W&B free tier)
