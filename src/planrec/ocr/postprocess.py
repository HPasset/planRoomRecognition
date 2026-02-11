from __future__ import annotations

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
    "sejour": ["sejour", "sej", "sejour/salon", "piece de vie"],
    "chambre": ["chambre", "ch", "chb"],
    "salle_de_bain": ["sdb", "salle de bain", "salle de bains"],
    "salle_de_douche": ["sdd", "salle de douche"],
    "salle_d_eau": ["salle d eau", "salle d'eau"],
    "wc": ["wc", "toilette", "toilettes"],
    "entree": ["entree"],
    "couloir": ["couloir"],
    "degagement": ["degagement", "dgm"],
    "bureau": ["bureau"],
    "cellier": ["cellier"],
    "buanderie": ["buanderie", "lingerie"],
    "dressing": ["dressing"],
    "garage": ["garage"],
    "balcon": ["balcon", "loggia"],
    "terrasse": ["terrasse"],
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


def _match_room_type(text_norm: str):
    text_clean = _clean_for_matching(text_norm)
    for alias, room_type in _ALIAS_INDEX:
        pattern = r"\b" + re.escape(alias).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text_clean):
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


def postprocess_ocr_items(items, confidence_min: float = 0.35):
    detections = []
    for item in items:
        text = item.get("text", "")
        confidence = float(item.get("confidence", 0.0))
        text_norm = normalize_text(text)

        if _should_skip(text_norm, confidence, confidence_min):
            continue

        room_type = _match_room_type(text_norm)
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

    return detections
