"""PaddleOCR wrapper — engine OCR principal du projet (français).

Méthode `.read(img_bgr, preprocess=True, detect_vertical=True)` retournant
`list[{"text", "bbox", "confidence"}]`, format consommé par
`src.planrec.ocr.postprocess.postprocess_ocr_items`.

PaddleOCR 3.x utilise la nouvelle API PaddleX (méthode `predict()`). Modèles
téléchargés automatiquement au premier appel (~500 MB dans ~/.paddlex/).

Multi-rotation : par défaut effectue 3 passes (0° + 90°CW + 90°CCW) pour
capturer les textes verticaux fréquents sur les plans architecturaux (WC,
Dgt, Galerie écrits sur la tranche). Coût : ×3 plus lent. Désactivable via
`detect_vertical=False` si performance critique et plan sans texte vertical.
"""
from __future__ import annotations
import warnings
from typing import Iterable

import cv2
import numpy as np

# PaddleOCR / PaddlePaddle émettent beaucoup de warnings inutiles
warnings.filterwarnings("ignore", category=UserWarning, module="paddleocr")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="paddle")

from paddleocr import PaddleOCR  # noqa: E402


def preprocess_for_plans(img_bgr, scale: int = 2):
    """Preprocessing optionnel pour OCR sur plans architecturaux.

    Upscale ×2 + GaussianBlur + adaptive threshold pour améliorer la lecture
    de textes très denses ou en faible contraste. En pratique, désactiver ce
    preprocess donne souvent de meilleurs résultats avec PaddleOCR car le
    threshold détruit les petits caractères. Garder ici pour compatibilité
    et pour les cas où il aide (textes très peu contrastés).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 5,
    )
    return thr, scale


class PaddleOCREngine:
    """Wrapper PaddleOCR 3.x — engine OCR principal du projet."""

    def __init__(self, langs: Iterable[str] = ("fr",), gpu: bool = False) -> None:
        """
        Args:
            langs: liste de langues. PaddleOCR utilise UNE langue (la première).
                   "fr" pour français.
            gpu: utiliser GPU si dispo (ignoré sur Mac MPS pour l'instant —
                 PaddlePaddle MPS support est encore limité).
        """
        lang_list = list(langs) or ["fr"]
        lang = lang_list[0]
        # PaddleOCR 3.5
        # - use_textline_orientation=True : essentiel pour lire les textes
        #   verticaux des plans architecturaux (ex: "WC", "Dgt" écrits sur le
        #   côté). Coût : +20-30% temps inférence. Indispensable pour notre
        #   use case.
        # - use_doc_orientation_classify=False : pas besoin de détecter
        #   orientation page (plan toujours au bon sens chez nous)
        # - use_doc_unwarping=False : pas besoin de déformer la page
        self._reader = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )

    def _ocr_single(
        self, img: np.ndarray, scale: int = 1,
    ) -> list[dict]:
        """OCR sur une image déjà préparée (BGR 3D). Compense le scale si != 1."""
        results = self._reader.predict(img)
        if not results:
            return []
        items: list[dict] = []
        for result in results:
            dt_polys = result.get("dt_polys", [])
            rec_texts = result.get("rec_texts", [])
            rec_scores = result.get("rec_scores", [])
            for poly, text, score in zip(dt_polys, rec_texts, rec_scores):
                pts = np.asarray(poly, dtype=np.float64)
                if scale != 1:
                    pts = pts / scale
                bbox_py = [[int(round(p[0])), int(round(p[1]))]
                           for p in pts.tolist()]
                items.append({
                    "text": str(text),
                    "bbox": bbox_py,
                    "confidence": float(score),
                })
        return items

    @staticmethod
    def _remap_bbox_from_cw_rotation(
        bbox: list[list[int]], orig_h: int,
    ) -> list[list[int]]:
        """Mappe une bbox de l'image rotée 90° CW vers l'image originale.

        Math : si image originale = (H, W), image rotée CW = (W, H).
        Un pixel original (x, y) devient (H-1-y, x) dans la rotée.
        Inverse : pixel rotated (x', y') ← original (y', H-1-x').
        """
        return [[int(y), int(orig_h - 1 - x)] for x, y in bbox]

    @staticmethod
    def _remap_bbox_from_ccw_rotation(
        bbox: list[list[int]], orig_w: int,
    ) -> list[list[int]]:
        """Mappe une bbox de l'image rotée 90° CCW vers l'image originale.

        Math : pixel original (x, y) → (y, W-1-x) dans rotée CCW.
        Inverse : pixel rotated (x', y') ← original (W-1-y', x').
        """
        return [[int(orig_w - 1 - y), int(x)] for x, y in bbox]

    def read(
        self, img_bgr: np.ndarray, preprocess: bool = True,
        detect_vertical: bool = True,
    ) -> list[dict]:
        """Run OCR + return list of {text, bbox, confidence} dicts.

        Args:
            img_bgr: input image (BGR)
            preprocess: apply preprocess_for_plans (grayscale + upscale + threshold)
            detect_vertical: si True, lance 2 OCR additionnels sur image rotée
                ±90° pour détecter les textes verticaux (WC, Dgt, Galerie, etc.).
                Coût : 3× plus lent (3 OCR passes).
        """
        if preprocess:
            img, scale = preprocess_for_plans(img_bgr)
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            img, scale = img_bgr, 1

        # Pass 1 : normal orientation
        hits = self._ocr_single(img, scale=scale)

        if not detect_vertical:
            return hits

        # Pass 2 + 3 : rotated 90° CW and CCW pour textes verticaux.
        # On utilise l'IMAGE BGR ORIGINALE (pas le preprocess) car le
        # preprocess perd souvent les petits textes.
        orig_h, orig_w = img_bgr.shape[:2]

        # CW rotation
        img_cw = cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
        hits_cw = self._ocr_single(img_cw, scale=1)
        for h in hits_cw:
            h["bbox"] = self._remap_bbox_from_cw_rotation(h["bbox"], orig_h)
            h["orientation"] = "vertical_90cw"

        # CCW rotation
        img_ccw = cv2.rotate(img_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        hits_ccw = self._ocr_single(img_ccw, scale=1)
        for h in hits_ccw:
            h["bbox"] = self._remap_bbox_from_ccw_rotation(h["bbox"], orig_w)
            h["orientation"] = "vertical_90ccw"

        # Concaténation des 3 passes — la déduplication potentielle (un texte
        # détecté dans plusieurs orientations) est gérée en aval par le
        # postprocess métier (qui mappe vers room_type et ignore les doublons).
        return hits + hits_cw + hits_ccw
