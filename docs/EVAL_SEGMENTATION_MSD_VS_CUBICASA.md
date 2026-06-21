# Éval segmentation — MSD vs CubiCasa (Stage A)

> Décideur = **mIoU sur de vrais plans FR**, pas l'architecture du dataset source.
> Contexte/licence : voir mémoire projet `reference_datasets_segmentation_licence`
> (CubiCasa5K = CC BY-NC, non-commercial → à retirer du pipeline d'un produit
> expédié ; MSD = CC BY 4.0, commercial OK).

## Pourquoi cette éval

MSD (Modified Swiss Dwellings) apporte un **renfort massif des murs** (≈594K
polygones `Structure` sur 5372 plans, rendus vectoriels propres) et une licence
commerciale. Mais c'est un **dataset de génération** : images de rendu *propres*,
**sans mobilier**, immeubles collectifs. Risque = **écart de domaine** avec les
plans FR réels (raster bruité, mobilier, hachures). On ne tranche donc pas à
l'intuition : on mesure sur du **vrai français**.

## Protocole

1. **Hold-out FR figé.** Réserver un sous-ensemble de plans FR annotés (segmentés)
   jamais vus à l'entraînement. **Même split** pour toutes les variantes.

2. **Trois variantes à comparer** — *fine-tune Stage B identique* (même train FR,
   mêmes hyperparams) sur chacune :
   - **(a) baseline** : Stage A CubiCasa → Stage B FR (l'existant).
   - **(b) MSD** : Stage A MSD (`configs/segmentation/stage_a_msd.yaml`) → Stage B FR.
   - **(c) FR seul** : pas de Stage A → Stage B FR (mesure l'apport réel d'un pré-train).

3. **Métriques** (via `src/segmentation/metrics.py`) sur le hold-out FR :
   - **mIoU global**.
   - **IoU par classe**, en insistant sur :
     - **`Wall`** (objectif n°1 du renfort MSD) ;
     - les **pièces rares** (Storage, Outdoor…) ;
     - **`Garage`** — absent de MSD, donc seul le FR Stage B l'enseigne : surveiller
       qu'il ne régresse pas en variante (b).

4. **Critère de décision.** Adopter MSD (variante b) si :
   - mIoU FR (b) **≥** mIoU FR (a), **et**
   - IoU `Wall` (b) **≥** IoU `Wall` (a).

   Sinon :
   - si (b) gagne sur `Wall` mais perd ailleurs → MSD **en complément** (concaténer
     les Stage A, ou MSD pour les murs + DWG-only conservé) ;
   - si l'écart de domaine domine (rendu propre vs réel) → ajouter de l'augmentation
     côté pipeline FR (bruit, hachures, dropout de traits) avant de reconclure.

5. **Garde-fou licence (indépendant des métriques).** Quel que soit le gagnant,
   **CubiCasa (CC BY-NC) ne doit pas rester dans le pipeline d'un modèle expédié.**
   Si (a) l'emporte techniquement, refaire (a) **sans CubiCasa** (MSD et/ou DWG-only)
   avant mise en production.

## Notes

- Murs déjà entraînés **DWG-only** chez batIA (vectoriel propre) : MSD `Structure`
  est du même type → cohérent. Comparer aussi, sur la classe `Wall`, **MSD vs
  DWG-only vs (MSD+DWG)**.
- Échelle : un `plan_id` MSD = un étage d'immeuble multi-logements (pièces plus
  petites à 768px). Si la variante (b) sous-performe sur les pièces, tester la
  rasterisation **par `apartment_id`** (plus proche de l'échelle maison FR) —
  raffinement du convertisseur, hors scope de ce protocole.
