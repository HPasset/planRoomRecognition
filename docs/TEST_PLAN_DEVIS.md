# Test plan — Éditeur Pièces & Devis quantitatif NF C 15-100

Périmètre : sections `🛠 Pièces à inclure dans le devis` + `💡 Devis quantitatif`
de `app/streamlit_app.py`. Utilisation "normale" par un électricien sur un plan
résidentiel typique (1 cuisine, 1 séjour, 2-3 chambres, 1 SDB, 1 WC, 1 dégagt).

## Préconditions communes

- Plan PDF/image chargé, OCR exécuté avec succès.
- OCR a détecté au moins : 1 Cuisine, 1 Séjour, 2 Chambres, 1 SDB, 1 WC.

---

## A. Initialisation de l'éditeur Pièces

| ID | Cas | Résultat attendu |
|---|---|---|
| A1 | Premier rendu après upload | Toutes les pièces OCR pré-cochées, type rempli depuis OCR, surface=0, notes=texte OCR brut |
| A2 | Upload sans détection OCR | 1 ligne "Chambre" par défaut + warning "Aucune pièce identifiée" |
| A3 | Re-upload du même plan (même hash) | État précédent (éditions + cochages) conservé |
| A4 | Upload d'un nouveau plan (hash différent) | Reset complet, perte des éditions du plan précédent |

## B. Ajout / suppression de pièces

| ID | Cas | Résultat attendu |
|---|---|---|
| B1 | Click "➕ Ajouter une pièce" | Nouvelle ligne en bas, type="Chambre", notes="(ajout manuel)", cochée |
| B2 | Click 🗑️ sur la 3ème ligne (parmi 5) | La 3ème ligne disparaît, les autres restent identiques |
| B3 | Décocher Inclure sur ligne 2 | Compteur "X/Y" mis à jour immédiatement (Y - 1) |
| B4 | Supprimer toutes les pièces puis "Générer devis" | Warning "Aucune pièce cochée" |
| B5 | Ajouter 3 pièces, supprimer celle du milieu | Les 2 restantes gardent leurs valeurs (pas de décalage de widget state) |
| B6 | Click "🔄 Réinitialiser" | Reconstruction depuis OCR, toutes éditions perdues |

## C. Changement de type & auto-indexation (#)

| ID | Cas | Résultat attendu |
|---|---|---|
| C1 | 3 Chambres détectées | Colonne # affiche "1", "2", "3" |
| C2 | 1 seule Cuisine | Colonne # vide pour la Cuisine (pas d'indice si unique) |
| C3 | Ajouter une 4ème pièce, changer type → Chambre | Colonne # affiche "1", "2", "3", "4" sur les 4 Chambres |
| C4 | Avoir 2 WC, supprimer 1 WC | La WC restante perd son indice (#vide) |
| C5 | Changer dropdown Chambre → WC sur la ligne ajoutée | Indice recalculé immédiatement : Chambres redeviennent 1,2,3 et WC devient 1 ou 2 selon contexte |

## D. Génération initiale du devis

| ID | Cas | Résultat attendu |
|---|---|---|
| D1 | Click "💡 Générer devis" avec 1 Cuisine + 3 Chambres + 1 WC | Tableau devis affiche les équipements NFC par pièce, avec indexation Chambre 1/2/3 |
| D2 | "Générer devis" sans pièce cochée | Warning, pas de tableau devis |
| D3 | Devis pour 1 WC seul | Équipements : 1 Prise + 1 Point lumineux + 1 Interrupteur (règles NFC WC) |
| D4 | Devis pour 1 Cuisine | Équipements NFC Cuisine : Prises (6), Alimentation spécialisée (3), Point lumineux, etc. |
| D5 | Activer "🦽 Norme handicap" et générer | Quantité de prises augmentée selon règles handicap NFC |

## E. Édition du devis

| ID | Cas | Résultat attendu |
|---|---|---|
| E1 | Changer Qté de 3 → 5 sur une ligne | Total TTC de la ligne recalculé immédiatement (5 × prix TTC unitaire) |
| E2 | Changer Prix HT de 25 → 30 | Prix TTC et Total TTC recalculés (30 × 1.20 = 36 TTC) |
| E3 | Changer TVA "Neuf 20%" → "Réno 10%" dans sidebar | Tous Prix TTC et Total TTC recalculés avec taux 10% |
| E4 | Changer Pièce d'une ligne (Cuisine → Séjour) | DataFrame sync via on_change, totaux inchangés (juste ré-affectation) |
| E5 | Changer Équipement d'une ligne (Prise → RJ45) | Libellé change, prix HT inchangé (à l'user de le mettre à jour) |

## F. Ajout / suppression d'équipements dans le devis

| ID | Cas | Résultat attendu |
|---|---|---|
| F1 | Sélectionner "Cuisine" + click "➕ Ajouter une ligne" | Nouvelle ligne ✏️ insérée APRÈS le dernier équipement Cuisine, pas à la fin |
| F2 | Click 🗑️ sur la 3ème ligne d'équipement (parmi 15) | Cette ligne disparaît, les autres restent |
| F3 | Ajouter ligne pour pièce avec 0 équipement existant | Ligne ajoutée à la fin du tableau (fallback) |
| F4 | Ajouter 3 lignes consécutives pour Chambre 2 | Toutes les 3 insérées après le dernier équipement Chambre 2, ordre préservé |
| F5 | Ajouter ligne pour "Autre" | Ligne ajoutée en fin, pas de groupe correspondant |

## G. Préservation lignes manuelles (manual_backup) à la regénération

| ID | Cas | Résultat attendu |
|---|---|---|
| G1 | Ajouter ligne manuelle Cuisine, click "Générer devis" | Ligne ✏️ préservée, positionnée après équipements Cuisine NFC |
| G2 | Ajouter ligne manuelle Cuisine + ajouter pièce WC + regen | Ligne manuelle Cuisine TOUJOURS après équipements Cuisine (pas à la fin) |
| G3 | Ajouter ligne manuelle WC, supprimer le WC, regen | Ligne manuelle pour WC inexistant → fallback append à la fin |
| G4 | 3 lignes manuelles pour pièces différentes + regen | Toutes préservées, chacune insérée au bon endroit |
| G5 | Modifier Qté/Prix d'une ligne ✏️ existante + regen | Modifications préservées (le manual_backup lit widget states) |

## H. Indexation des pièces dans le devis

| ID | Cas | Résultat attendu |
|---|---|---|
| H1 | 3 Chambres → devis | Lignes "Chambre 1", "Chambre 2", "Chambre 3" |
| H2 | 1 seule Cuisine → devis | Lignes "Cuisine" (sans indice) |
| H3 | Ajouter 4ème Chambre + regen | "Chambre 1, 2, 3, 4" |
| H4 | 2 Chambres + 1 WC → devis | "Chambre 1, 2" + "WC" (sans indice WC car seul) |
| H5 | 2 WC + 3 Chambres → devis | "Chambre 1, 2, 3" + "WC 1", "WC 2" |

## I. Calcul des totaux

| ID | Cas | Résultat attendu |
|---|---|---|
| I1 | Total HT global | = Σ(qty × Prix HT) sur toutes les lignes affichées |
| I2 | Total TTC global | = Total HT × (1 + taux TVA), arrondi à 2 décimales |
| I3 | Changer TVA → vérifier totaux | Recalcul instantané |
| I4 | Décocher 1 pièce + regen | Équipements absents du devis, total diminué |
| I5 | Mettre Qté=0 sur 1 ligne | Total TTC de cette ligne = 0, total global diminué |

## J. Export CSV

| ID | Cas | Résultat attendu |
|---|---|---|
| J1 | Click "📥 Télécharger devis CSV" | Fichier généré, header : Pièce;Équipement;Qté;HT;TTC;Total TTC |
| J2 | Contenu CSV | 1 ligne par équipement, séparateur `;`, ligne TOTAL en bas |
| J3 | Modifier Qté/Prix avant export | CSV reflète les valeurs courantes (pas les défauts NFC) |
| J4 | Caractères spéciaux dans Pièce (ex: "Salle d'eau") | Échappés correctement par csv.writer |

## K. Cas limites & robustesse

| ID | Cas | Résultat attendu |
|---|---|---|
| K1 | Ajouter 30 pièces | UI reste responsive, scrolling OK |
| K2 | Notes OCR > 50 chars | Tronquées dans le champ texte (mais valeur complète si l'user étend) |
| K3 | Click rapide multiple sur 🗑️ | 1 suppression par click, pas de double-suppression |
| K4 | Cocher/décocher rapidement Inclure | État final correct, pas de glitch |
| K5 | Supprimer 1 pièce qui a des lignes manuelles ✏️ dans le devis + regen | Lignes manuelles préservées (fallback en fin de tableau) |
| K6 | Recharger la page (F5) | session_state perdu (comportement Streamlit normal), repartir de zéro |

---

## Bugs déjà identifiés et corrigés (régression à vérifier)

| ID | Bug | Cas de régression |
|---|---|---|
| R1 | 🗑️ supprime la mauvaise ligne | B2, F2 |
| R2 | WC manuel indexé "4" au lieu de "2" | C3, C5, H3 |
| R3 | WC manuel devient "Chambre 4" après "Générer devis" | C5 + D1 enchaînés |
| R4 | Ligne manuelle cuisine se retrouve en fin après regen | G2 |
| R5 | st.status fait sauter la page à chaque interaction | (cas non-fonctionnel : observer l'UI pendant B3) |
