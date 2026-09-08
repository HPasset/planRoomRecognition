from __future__ import annotations

import difflib
import re
import unicodedata


_SURFACE_ONLY_RE = re.compile(r"^\d+[.,]?\d*\s*m2$")
_NUMERIC_RE = re.compile(r"^\d+[.,]?\d*$")

_IGNORE_PHRASES = [
    "surface interieure",
    "surface approximative",
    "surface approx",
    "approximative",
    "approx",
]

_ROOM_ALIASES = {
    "cuisine": ["cuisine"],
    "salon": ["salon"],
    "sejour": ["sejour", "sej", "sejour/salon", "piece de vie",
                "espace de vie",
                "espace a vivre", "espaces a vivre",  # "Espace à vivre"
                ],
    "chambre": [
        "chambre", "ch", "chb",
        "suite", "suite parentale", "suite parents",
    ],
    "salle_de_bain": ["sdb", "salle de bain", "salle de bains",
                       "bains", "salle de bain principale"],
    "salle_de_douche": ["sdd", "salle de douche"],
    "salle_d_eau": [
        "salle d eau", "salle d'eau",
        "sde", "s d e", "s.d.e",   # abréviations avec/sans ponctuation
        "soe",                      # erreur OCR fréquente (D lu comme O)
        "s eau", "s.eau",           # variante 'S.Eau'
    ],
    "wc": ["wc", "toilette", "toilettes"],
    "entree": ["entree", "vestibule"],
    "couloir": ["couloir", "galerie"],
    "degagement": ["degagement", "degag", "dgm", "dgt", "deg",
                    "hall", "hall d entree", "hall d'entree",
                    ],
    "bureau": ["bureau"],
    "cellier": [
        "cellier",
        # Alias multi-mots : Cellier/Buanderie souvent écrits sur 2 lignes
        # désignent UNE seule pièce multi-usage. merge_multiline_aliases
        # se charge de fusionner les 2 hits OCR adjacents avant matching.
        "cellier buanderie",
        "cellier / buanderie",
        "buanderie cellier",
        # Rangement / stockage — abréviations FR pour zone de stockage
        "rang", "rangement", "rangements", "stockage",
        # Abri de jardin (annexe extérieure servant de stockage)
        "abri de jardin", "abri jardin", "abris de jardin",
    ],
    "buanderie": ["buanderie", "lingerie"],
    "atelier": ["atelier"],
    "dressing": ["dressing", "dress"],
    "garage": ["garage"],
    "balcon": ["balcon", "loggia"],
    "terrasse": ["terrasse", "allee", "allee piétonne", "allee couverte",
                  "porche", "auvent",
                  # Annexe extérieure (mappe à Outdoor via FR_TO_C2)
                  "carport", "car port",
                  ],
    "palier": ["palier"],
    "nid": ["nid"],
}

_INDEXED_ROOM_TYPES = {"chambre"}


def normalize_text(text: str) -> str:
    s = text.strip().lower()
    s = s.replace(f"m\u00b2", "m2").replace("m^2", "m2")
    s = re.sub(r"([0-9])\s*n2\b", r"\1 m2", s)
    s = re.sub(r"\bn2\b", "m2", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_alias(alias: str) -> str:
    return normalize_text(alias)


def _build_alias_index():
    pairs = []
    for room_type, aliases in _ROOM_ALIASES.items():
        for alias in aliases:
            alias_norm = _normalize_alias(alias)
            if alias_norm:
                pairs.append((alias_norm, room_type))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


_ALIAS_INDEX = _build_alias_index()
_IGNORE_PHRASES_NORM = [_normalize_alias(p) for p in _IGNORE_PHRASES]


def _clean_for_matching(text_norm: str) -> str:
    text_norm = re.sub(r"\b\d+[.,]?\d*\s*m2\b", " ", text_norm)
    text_norm = re.sub(r"\s+", " ", text_norm).strip()
    return text_norm


def _match_room_type(text_norm: str, fuzzy: bool = False,
                      fuzzy_cutoff: float = 0.80):
    """Match a room_type in the text.

    Strategy:
      1. Exact word/phrase match (fast path).
      2. If fuzzy=True and no exact match: fuzzy match each word in text
         against single-word aliases. Multi-word aliases (e.g. "salle de bain")
         skip the fuzzy fallback — they'd produce too many false positives.
         Uses difflib.SequenceMatcher (stdlib). Cutoff 0.80 ≈ 1 char error
         on a 5-7 letter word like "chambre"/"cuisine".
    """
    text_clean = _clean_for_matching(text_norm)
    # 1. Exact path
    for alias, room_type in _ALIAS_INDEX:
        pattern = r"\b" + re.escape(alias).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text_clean):
            return room_type

    if not fuzzy:
        return None

    # 2. Fuzzy fallback — only on single-token aliases, only for words >= 6
    # chars. Pourquoi 6 chars min : sur des mots courts (4-5 chars), le ratio
    # SequenceMatcher devient trompeur. Ex: "salle" vs "allee" → ratio 0.80
    # (partagent "alle") → faux positif. À 6+ chars la robustesse est OK.
    # Les vrais cas légitimes (chamgre/chambre, cuisine, garage...) font tous
    # 6 chars ou plus.
    single_aliases = [(a, rt) for a, rt in _ALIAS_INDEX if " " not in a]
    words = re.findall(r"[a-z]+", text_clean)
    for word in words:
        if len(word) < 6:  # mots courts trop ambigus pour le fuzzy
            continue
        for alias, room_type in single_aliases:
            if len(alias) < 6:
                continue
            ratio = difflib.SequenceMatcher(None, word, alias).ratio()
            if ratio >= fuzzy_cutoff:
                return room_type
    return None


def _extract_room_index(room_type: str, text_norm: str):
    if room_type not in _INDEXED_ROOM_TYPES:
        return None
    match = re.search(r"\bchambre\s*([0-9]{1,3})\b", text_norm)
    if match:
        return match.group(1)
    return None


def _should_skip(text_norm: str, confidence: float, confidence_min: float) -> bool:
    if confidence < confidence_min:
        return True
    if not text_norm:
        return True
    if len(text_norm) > 40:
        return True
    if _NUMERIC_RE.fullmatch(text_norm):
        return True
    if _SURFACE_ONLY_RE.fullmatch(text_norm):
        return True
    if any(p in text_norm for p in _IGNORE_PHRASES_NORM):
        return True
    return False


def _bbox_centroid(bbox: list[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _bbox_height(bbox: list[list[float]]) -> float:
    ys = [p[1] for p in bbox]
    return max(ys) - min(ys)


def _bbox_text_height(bbox: list[list[float]]) -> float:
    """Hauteur réelle d'un texte OCR, robuste à l'orientation.

    Pour un bbox de texte, la "hauteur des caractères" est toujours la PLUS
    PETITE dimension du bbox — peu importe si le texte est horizontal,
    vertical (rotation 90°/270°), ou en biais.

    Ex: "Galerie" écrit verticalement, après remappage des coords vers l'image
    originale, donne un bbox de ~25 × 80 px (étroit en x, long en y). On veut
    bien 25 comme "hauteur du texte", pas 80.
    """
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def _merge_bboxes(b1: list[list[float]], b2: list[list[float]]) -> list[list[float]]:
    all_pts = b1 + b2
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return [
        [int(x_min), int(y_min)],
        [int(x_max), int(y_min)],
        [int(x_max), int(y_max)],
        [int(x_min), int(y_max)],
    ]


def merge_multiline_aliases(items: list[dict], proximity_factor: float = 2.5) -> list[dict]:
    """Fusionne les hits OCR adjacents qui forment ensemble un alias multi-mots.

    Cas typique : "Salle d'eau" écrit sur 2 lignes ('Salle' au-dessus, 'd'eau'
    en-dessous) → l'OCR sort 2 hits qui isolément ne matchent aucun alias.
    Cette fonction détecte les paires de hits dont la concaténation forme un
    alias multi-mots connu, et les fusionne en un seul hit.

    Args:
        items: liste de hits OCR bruts (avec keys 'text', 'bbox', 'confidence')
        proximity_factor: distance max entre centroïdes en multiples de la
                          hauteur moyenne des hits (2.5 = ~2-3 lignes d'écart max)

    Returns:
        Nouvelle liste de hits (potentiellement plus courte si fusions effectuées).
    """
    # Précompute multi-word aliases (normalized)
    multi_word: list[tuple[str, str]] = []
    for room_type, aliases in _ROOM_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if " " in alias_norm and len(alias_norm.split()) >= 2:
                multi_word.append((alias_norm, room_type))
    if not multi_word:
        return list(items)

    out = list(items)
    consumed: set[int] = set()
    new_items: list[dict] = []

    for i, hit_i in enumerate(out):
        if i in consumed:
            continue
        text_i_norm = normalize_text(hit_i.get("text", ""))
        if not text_i_norm or len(text_i_norm) < 2:
            new_items.append(hit_i)
            continue

        bbox_i = hit_i.get("bbox")
        if not bbox_i or len(bbox_i) < 3:
            new_items.append(hit_i)
            continue
        cx_i, cy_i = _bbox_centroid(bbox_i)
        h_i = _bbox_height(bbox_i)

        merged_with_j: int | None = None
        merged_combined: str | None = None
        merged_raw: str | None = None

        for j, hit_j in enumerate(out):
            if j == i or j in consumed:
                continue
            text_j_norm = normalize_text(hit_j.get("text", ""))
            if not text_j_norm or len(text_j_norm) < 2:
                continue
            bbox_j = hit_j.get("bbox")
            if not bbox_j or len(bbox_j) < 3:
                continue
            cx_j, cy_j = _bbox_centroid(bbox_j)
            h_j = _bbox_height(bbox_j)

            avg_h = (h_i + h_j) / 2.0
            if avg_h <= 0:
                continue
            dist = ((cx_i - cx_j) ** 2 + (cy_i - cy_j) ** 2) ** 0.5
            if dist > avg_h * proximity_factor:
                continue

            # Essai des 2 ordres (i puis j, et j puis i)
            for combined in (f"{text_i_norm} {text_j_norm}",
                              f"{text_j_norm} {text_i_norm}"):
                # Vérifie qu'un alias multi-mots est inclus dans la concat
                for alias_norm, _room_type in multi_word:
                    if alias_norm in combined:
                        merged_with_j = j
                        merged_combined = combined
                        merged_raw = (
                            f"{hit_i.get('text', '')} {hit_j.get('text', '')}"
                            if combined.startswith(text_i_norm)
                            else f"{hit_j.get('text', '')} {hit_i.get('text', '')}"
                        )
                        break
                if merged_with_j is not None:
                    break
            if merged_with_j is not None:
                break

        if merged_with_j is not None:
            consumed.add(i)
            consumed.add(merged_with_j)
            hit_j = out[merged_with_j]
            new_items.append({
                "text": merged_raw,
                "bbox": _merge_bboxes(bbox_i, hit_j["bbox"]),
                "confidence": min(
                    float(hit_i.get("confidence", 0.0)),
                    float(hit_j.get("confidence", 0.0)),
                ),
            })
        else:
            new_items.append(hit_i)

    return new_items


def _cluster_keep_best(
    items: list[dict],
    group_key,
    threshold_fn,
) -> list[dict]:
    """Regroupe `items` par `group_key(item)` (items sans clé = ignorés), puis
    dans chaque groupe trie par confidence DESC et clusterise par proximité de
    centroïde bbox (distance < threshold_fn(item, cluster_head)). Garde le 1er
    (donc le plus confiant) de chaque cluster."""
    if not items:
        return items

    by_key: dict[str, list[dict]] = {}
    for item in items:
        key = group_key(item)
        if not key:
            continue
        by_key.setdefault(key, []).append(item)

    out: list[dict] = []
    for key, group in by_key.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        # Trie par confidence DESC pour donner la priorité aux items sûrs
        group_sorted = sorted(group, key=lambda h: -float(h.get("confidence", 0)))
        # Clusters de proximité géographique
        clusters: list[list[dict]] = []
        for item in group_sorted:
            bbox = item.get("bbox", [])
            if not bbox or len(bbox) < 3:
                clusters.append([item])
                continue
            cx, cy = _bbox_centroid(bbox)
            placed = False
            for cluster in clusters:
                head_bbox = cluster[0].get("bbox", [])
                if not head_bbox or len(head_bbox) < 3:
                    continue
                head_cx, head_cy = _bbox_centroid(head_bbox)
                dist = ((cx - head_cx) ** 2 + (cy - head_cy) ** 2) ** 0.5
                if dist < threshold_fn(item, cluster[0]):
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])
        # Garde le 1er (plus confiant) de chaque cluster
        for cluster in clusters:
            out.append(cluster[0])
    return out


def deduplicate_hits(items: list[dict],
                      distance_threshold: float = 50.0) -> list[dict]:
    """Déduplique les hits OCR identiques (même texte normalisé + position proche).

    Cas typique : le multi-rotation de PaddleOCR (3 passes : normal + 90°CW +
    90°CCW) détecte le même texte horizontal 3 fois dans des bboxes très
    proches. Cette fonction garde uniquement le hit de plus haute confidence
    pour chaque cluster (même texte + proximité géographique).

    Args:
        items: hits OCR bruts
        distance_threshold: distance max entre centroïdes (px) pour considérer
                            2 hits comme doublons (50px convient sur plans
                            ~1500px de large)

    Returns:
        Liste dédupliquée.
    """
    return _cluster_keep_best(
        items,
        group_key=lambda h: normalize_text(h.get("text", "")),
        threshold_fn=lambda item, head: distance_threshold,
    )


def deduplicate_detections_by_room_type(
    detections: list[dict],
    min_distance_threshold_px: float = 80.0,
    height_multiplier: float = 5.0,
) -> list[dict]:
    """Déduplique les détections matchées partageant le même room_type ET
    géographiquement proches.

    Résout les cas typiques :
      - "Chambre" + "Chambr" (lecture partielle) sur la même chambre
      - "Garage" + "e Gara" (fragment) sur le même garage
      - "Espace de Vie" + "Séjour" sur la MÊME pièce open-space
      - Et PRÉSERVE : "Galerie" vs "Couloir" sur 2 zones distinctes,
        3 chambres voisines avec labels "Chambre" identiques

    Seuil adaptatif basé sur la hauteur du label OCR :
      seuil = max(80 px, 5 × hauteur moyenne des 2 labels)

    Logique : 2 labels OCR du même room_type sont "dans la même pièce" si
    leur distance est < 5× la hauteur du texte (un label fait typiquement
    20-30 px de haut, donc seuil 100-150 px = ~1 pièce). Sur plans avec
    pièces resserrées, ce seuil adaptatif évite les faux merges.

    Args:
        detections: liste de détections post-matching
        min_distance_threshold_px: plancher absolu (80 px par défaut), pour
                                    éviter un seuil ridiculement petit si
                                    labels minuscules
        height_multiplier: combien de hauteurs de texte = même pièce (5 par
                           défaut, ajuster si pièces très serrées ou très grandes)

    Returns:
        Liste dédupliquée — garde le plus confiant de chaque cluster.
    """
    def _threshold(item: dict, head: dict) -> float:
        # Utilise text_height (= min dim du bbox) au lieu de height pour être
        # robuste aux textes verticaux (remappés du multi-rotation). Seuil
        # adaptatif : max(plancher, k × hauteur moyenne texte).
        avg_h = (_bbox_text_height(item.get("bbox", []))
                 + _bbox_text_height(head.get("bbox", []))) / 2.0
        return max(min_distance_threshold_px, height_multiplier * avg_h)

    return _cluster_keep_best(
        detections,
        group_key=lambda d: d.get("room_type"),
        threshold_fn=_threshold,
    )


def postprocess_ocr_items(items, confidence_min: float = 0.35,
                           fuzzy: bool = False, fuzzy_cutoff: float = 0.80,
                           fuzzy_min_confidence: float = 0.50):
    """Pipeline complet OCR brut → détections de pièces.

    Args:
        items: hits OCR bruts
        confidence_min: filtre les hits avec confidence < ce seuil
        fuzzy: active le fuzzy matching pour gérer les erreurs OCR de 1-2 chars
        fuzzy_cutoff: cutoff du fuzzy matching (0.72 = ~2 erreurs tolérées)
        fuzzy_min_confidence: le fuzzy matching n'est appliqué QUE si la
            confidence OCR du hit est ≥ ce seuil. Empêche les bruits OCR
            faibles (ex: 'ereee' conf 0.30) de matcher par hasard 'entree'.
    """
    # Étape 1 : déduplication des hits du multi-rotation (PaddleOCR 3-pass
    # détecte les textes horizontaux 3 fois)
    items = deduplicate_hits(items)
    # Étape 2 : fusion des hits adjacents formant un alias multi-mots
    # (ex: "Salle"+"d'eau" sur 2 lignes → "Salle d'eau")
    items = merge_multiline_aliases(items)

    detections = []
    for item in items:
        text = item.get("text", "")
        confidence = float(item.get("confidence", 0.0))
        text_norm = normalize_text(text)

        if _should_skip(text_norm, confidence, confidence_min):
            continue

        # Le fuzzy n'est activé que pour les hits avec confidence raisonnable.
        # En dessous (genre 0.30), le hit est probablement du bruit OCR pur
        # et le fuzzy matchera par hasard un alias (ex: 'ereee' → 'entree').
        use_fuzzy = fuzzy and confidence >= fuzzy_min_confidence
        room_type = _match_room_type(text_norm, fuzzy=use_fuzzy,
                                       fuzzy_cutoff=fuzzy_cutoff)
        if not room_type:
            continue

        detection = {
            "room_type": room_type,
            "raw_text": text,
            "confidence": confidence,
            "bbox": item.get("bbox"),
        }

        room_index = _extract_room_index(room_type, text_norm)
        if room_index:
            detection["room_index"] = room_index

        detections.append(detection)

    # Étape finale : déduplication par room_type + proximité géographique
    # (gère "Chambre"+"Chambr" sur même pièce, "Espace de Vie"+"Séjour"
    # sur même open-space, etc.)
    detections = deduplicate_detections_by_room_type(detections)
    return detections
