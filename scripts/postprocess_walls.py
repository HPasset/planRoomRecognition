"""Post-traitement des masques de murs prédits par Mask2Former.

Stage A (nettoyage raster) :
- close_gaps()    : ferme les trous (rose des vents, cotes, etc.) par closing
- filter_cc()     : supprime les petites composantes (texte, bruit) par
                    seuil surface + élongation PCA

Stage B (vectorisation) :
- skeletonize_walls() : skeleton 1px du centre des murs
- vectorize_skeleton() : extrait des segments via HoughLinesP

Usage :
    from scripts.postprocess_walls import (
        close_gaps, filter_cc, skeletonize_walls, vectorize_skeleton,
    )
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.morphology import skeletonize


# ============================================================================
# Stage A — Raster cleanup
# ============================================================================

def close_gaps(mask: np.ndarray, kernel_size: int = 11) -> np.ndarray:
    """Morphological closing pour combler les trous dans les murs continus
    (symboles parasites, cotes, croisements).

    kernel_size en pixels — pour combler un trou de N px, kernel ≥ N+2.
    Par défaut 11px ferme jusqu'à des trous de ~10px (typique rose des vents).
    """
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, k)


def _component_aspect_ratio(coords: np.ndarray) -> float:
    """Aspect ratio de la composante via PCA. Élevé = élongé (mur),
    proche de 1 = rond (texte, petit blob)."""
    if len(coords) < 5:
        return 1.0
    coords = coords.astype(np.float32)
    coords -= coords.mean(axis=0)
    cov = np.cov(coords.T)
    eigvals = np.linalg.eigvalsh(cov)
    if eigvals[0] < 1e-6:
        return 100.0  # purement linéaire
    return float(np.sqrt(eigvals[1] / eigvals[0]))


def filter_cc(
    mask: np.ndarray,
    min_area: int = 200,
    min_aspect_ratio: float = 3.0,
) -> np.ndarray:
    """Connected-components filter sur le mask binaire.

    Supprime les composantes :
    - dont l'aire < min_area (texte, petit bruit)
    - OU dont l'aspect ratio PCA < min_aspect_ratio (formes compactes :
      labels, pictogrammes ronds, tables, etc.) — sauf si très grandes

    Retourne le masque nettoyé (uint8, 0/1).
    """
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8,
    )
    keep = np.zeros(n_labels, dtype=bool)
    keep[0] = False  # background
    for i in range(1, n_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area:
            continue
        coords = np.column_stack(np.where(labels == i))
        ar = _component_aspect_ratio(coords)
        # Garde si très grande (mur principal) OU si élongée
        if area > 2000 or ar >= min_aspect_ratio:
            keep[i] = True
    out = keep[labels].astype(np.uint8)
    return out


# ============================================================================
# Stage B — Skeletonisation + vectorisation
# ============================================================================

def skeletonize_walls(mask: np.ndarray) -> np.ndarray:
    """Skeleton 1px au centre des murs (uint8, 0/1)."""
    return skeletonize(mask.astype(bool)).astype(np.uint8)


def vectorize_skeleton(
    skel: np.ndarray,
    hough_threshold: int = 30,
    min_line_length: int = 25,
    max_line_gap: int = 15,
) -> list[tuple[int, int, int, int]]:
    """Extrait des segments de droite via HoughLinesP.

    Retourne une liste de [(x1, y1, x2, y2), ...].
    """
    skel255 = (skel * 255).astype(np.uint8)
    lines = cv2.HoughLinesP(
        skel255, rho=1, theta=np.pi / 180,
        threshold=hough_threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if lines is None:
        return []
    return [tuple(int(v) for v in line[0]) for line in lines]


def draw_segments(
    image_shape: tuple[int, int],
    segments: list[tuple[int, int, int, int]],
    thickness: int = 3,
) -> np.ndarray:
    """Dessine les segments en blanc sur fond noir (mask uint8 0/255)."""
    canvas = np.zeros(image_shape[:2], dtype=np.uint8)
    for x1, y1, x2, y2 in segments:
        cv2.line(canvas, (x1, y1), (x2, y2), 255, thickness, cv2.LINE_AA)
    return canvas
