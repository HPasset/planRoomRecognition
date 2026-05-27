"""Post-processing of room polygons for cleaner visual rendering.

Two transforms (composable):
  1. simplify_dp() — Douglas-Peucker, reduces 200+ noisy vertices to ~10 clean
     ones. Epsilon is expressed as a percentage of the polygon perimeter so the
     same tolerance scales correctly across plan resolutions.
  2. snap_axis_aligned() — for each edge whose angle (mod 90°) is within a
     small tolerance of 0°/90°, snap its endpoints so the edge becomes strictly
     horizontal or vertical. Yields the "architect" look. Best applied AFTER
     simplification (otherwise tiny noisy edges get aligned and the polygon
     becomes a mess).

Both operate on polygons of shape list[list[int]] = [[x, y], ...].
"""
from __future__ import annotations
import math

import cv2
import numpy as np


def simplify_dp(polygon_xy: list[list[int]], epsilon_pct: float) -> list[list[int]]:
    """Douglas-Peucker simplification.

    Args:
        polygon_xy: [[x, y], ...] integer coords
        epsilon_pct: tolerance as % of perimeter (e.g. 1.0 = 1% of perimeter).
                     0 = no simplification (returns input unchanged).

    Returns:
        Simplified polygon, guaranteed ≥3 vertices.
    """
    if epsilon_pct <= 0 or len(polygon_xy) < 4:
        return polygon_xy

    pts = np.asarray(polygon_xy, dtype=np.int32).reshape(-1, 1, 2)
    perimeter = float(cv2.arcLength(pts, closed=True))
    if perimeter <= 0:
        return polygon_xy

    epsilon = epsilon_pct / 100.0 * perimeter
    simplified = cv2.approxPolyDP(pts, epsilon, closed=True)
    out = simplified.reshape(-1, 2).tolist()

    # cv2 can over-simplify down to <3 verts on tiny shapes — guard
    if len(out) < 3:
        return polygon_xy
    return [[int(p[0]), int(p[1])] for p in out]


def _edge_angle_deg(p0, p1) -> float:
    """Angle in degrees, in [0, 180). 0 = horizontal, 90 = vertical."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    if dx == 0 and dy == 0:
        return 0.0
    return math.degrees(math.atan2(dy, dx)) % 180.0


def snap_axis_aligned(
    polygon_xy: list[list[int]], tolerance_deg: float = 12.0,
) -> list[list[int]]:
    """For each edge whose angle is within `tolerance_deg` of 0° or 90°,
    snap the edge to be strictly horizontal or vertical.

    Strategy: walk edges in order. For each edge (i, i+1):
      - if near horizontal → set y[i+1] = y[i]
      - if near vertical   → set x[i+1] = x[i]
    This propagates: the next vertex inherits the snapped coord. Cumulative
    drift is generally acceptable for visual polish; for accuracy-critical use
    cases (e.g. m² calculation) prefer the unsnapped polygon.

    Args:
        polygon_xy: [[x, y], ...]
        tolerance_deg: edges within ±tolerance° of horizontal/vertical are snapped

    Returns:
        Polygon of the same length as input.
    """
    n = len(polygon_xy)
    if n < 3:
        return polygon_xy

    out = [list(p) for p in polygon_xy]
    for i in range(n):
        j = (i + 1) % n
        p0 = out[i]
        p1 = out[j]
        angle = _edge_angle_deg(p0, p1)

        # Near horizontal: angle close to 0° or 180°
        if angle <= tolerance_deg or angle >= 180.0 - tolerance_deg:
            out[j][1] = p0[1]
        # Near vertical: angle close to 90°
        elif abs(angle - 90.0) <= tolerance_deg:
            out[j][0] = p0[0]

    return [[int(p[0]), int(p[1])] for p in out]


def _compute_dark_mask(
    gray: np.ndarray,
    strategy: str,
    dark_threshold: int | None,
    morph_open_kernel: int,
) -> np.ndarray:
    """Compute binary mask of dark features (walls).

    Strategies:
      - "manual": fixed global threshold (sensitive to plan style)
      - "adaptive": local thresholding by Gaussian-weighted neighborhood,
                    adapts to intensity variations across the plan
      - "otsu": global threshold chosen automatically by Otsu's method
                from the image histogram
    """
    if strategy == "manual":
        if dark_threshold is None:
            return np.full_like(gray, 255)
        _, mask = cv2.threshold(gray, dark_threshold, 255, cv2.THRESH_BINARY_INV)
    elif strategy == "adaptive":
        mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, blockSize=31, C=5,
        )
    elif strategy == "otsu":
        _, mask = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
    else:
        raise ValueError(f"Unknown threshold strategy: {strategy}")

    if morph_open_kernel and morph_open_kernel > 1:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (morph_open_kernel, morph_open_kernel),
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def extract_lines_from_image(
    image_bgr: np.ndarray,
    algorithm: str = "hough",
    canny_low: int = 50,
    canny_high: int = 150,
    min_line_length: int = 50,
    max_line_gap: int = 10,
    threshold: int = 80,
    dark_threshold: int | None = 150,
    threshold_strategy: str = "manual",
    morph_open_kernel: int = 3,
    axis_aligned_only: bool = True,
    axis_tolerance_deg: float = 10.0,
) -> list[tuple[int, int, int, int]]:
    """Extract straight wall lines from a plan image via Canny + Hough.

    Used as a robust alternative when the model's Wall mask is empty (typical
    on FR plans where Wall was not annotated during CVAT labeling). Walls on
    architectural plans are visually obvious (thick black lines) and can be
    reliably extracted without any model.

    Multi-stage filtering to reduce false positives (furniture, stairs, arcs,
    dimension lines):
        1. Dark thresholding: keep only pixels darker than `dark_threshold`
           (walls are the darkest features).
        2. Morphological opening: remove thin features (dimensions, hatches).
        3. Length filter via `min_line_length`.
        4. Axis-aligned filter: keep only lines within `axis_tolerance_deg` of
           horizontal or vertical (most walls are H/V; diagonals = stairs, arcs).

    Args:
        image_bgr: original plan image (HxWx3, uint8)
        canny_low/high: Canny hysteresis thresholds
        min_line_length: drop segments shorter than this (px)
        max_line_gap: allowed gap between collinear points
        threshold: Hough accumulator threshold
        dark_threshold: pixels with intensity > this are ignored (None = disabled)
        morph_open_kernel: opening kernel size for morphology (1 = disabled)
        axis_aligned_only: keep only H/V lines (filters stairs, arcs, diagonals)
        axis_tolerance_deg: tolerance for the axis-aligned filter

    Returns:
        List of (x1, y1, x2, y2) segments in original image coordinates.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    if algorithm == "lsd":
        # LSD operates directly on grayscale, no Canny/threshold needed.
        # Optional: pre-process with dark mask for noise reduction.
        src = gray
        if threshold_strategy != "manual" or dark_threshold is not None:
            src = _compute_dark_mask(
                gray, threshold_strategy, dark_threshold, morph_open_kernel,
            )
        lsd = cv2.createLineSegmentDetector()
        result = lsd.detect(src)
        lines = result[0] if result and result[0] is not None else None
        if lines is None:
            return []
        out: list[tuple[int, int, int, int]] = []
        for l in lines:
            x1, y1, x2, y2 = l[0]
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_line_length:
                continue
            out.append((int(round(x1)), int(round(y1)),
                        int(round(x2)), int(round(y2))))
    else:
        # Hough path: Canny on (optionally masked) image, then HoughLinesP
        if threshold_strategy == "manual" and dark_threshold is None:
            edges = cv2.Canny(gray, canny_low, canny_high)
        else:
            mask = _compute_dark_mask(
                gray, threshold_strategy, dark_threshold, morph_open_kernel,
            )
            edges = cv2.Canny(mask, canny_low, canny_high)
        raw = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180, threshold=threshold,
            minLineLength=min_line_length, maxLineGap=max_line_gap,
        )
        if raw is None:
            return []
        out = [tuple(map(int, l[0])) for l in raw]

    # Stage 4: axis-aligned filter
    if axis_aligned_only:
        filtered: list[tuple[int, int, int, int]] = []
        for x1, y1, x2, y2 in out:
            dx, dy = x2 - x1, y2 - y1
            if dx == 0 and dy == 0:
                continue
            angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
            near_horizontal = angle <= axis_tolerance_deg or angle >= 180.0 - axis_tolerance_deg
            near_vertical = abs(angle - 90.0) <= axis_tolerance_deg
            if near_horizontal or near_vertical:
                filtered.append((x1, y1, x2, y2))
        out = filtered

    return out


def extract_wall_lines(
    wall_mask: np.ndarray,
    min_line_length: int = 30,
    max_line_gap: int = 10,
    threshold: int = 50,
) -> list[tuple[int, int, int, int]]:
    """Extract straight wall segments from a binary wall mask via Hough.

    Args:
        wall_mask: (H, W) uint8, non-zero = wall
        min_line_length: drop segments shorter than this (px)
        max_line_gap: allowed gap between collinear points to consider one line
        threshold: Hough accumulator threshold

    Returns:
        List of [(x1, y1, x2, y2), ...] segments.
    """
    if wall_mask.dtype != np.uint8:
        wall_mask = wall_mask.astype(np.uint8)
    if wall_mask.max() == 1:
        wall_mask = wall_mask * 255

    # Edges of the wall mask (gives a thin "skeleton" around wall boundaries)
    edges = cv2.Canny(wall_mask, 50, 150)
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=threshold,
        minLineLength=min_line_length, maxLineGap=max_line_gap,
    )
    if lines is None:
        return []
    return [tuple(map(int, l[0])) for l in lines]


def _angle_of_line(x1: float, y1: float, x2: float, y2: float) -> float:
    """In [0, 180)."""
    if x2 == x1 and y2 == y1:
        return 0.0
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _point_to_line_dist(px: float, py: float,
                         x1: float, y1: float, x2: float, y2: float) -> float:
    """Perpendicular distance from (px, py) to the infinite line through (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    denom = math.hypot(dx, dy)
    if denom == 0:
        return math.hypot(px - x1, py - y1)
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / denom


def _line_intersection(
    l1: tuple[float, float, float, float],
    l2: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    """Intersection of two infinite lines (each given as 4 coords).
    Returns None if parallel."""
    x1, y1, x2, y2 = l1
    x3, y3, x4, y4 = l2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def snap_polygon_to_walls(
    polygon_xy: list[list[int]],
    wall_lines: list[tuple[int, int, int, int]],
    tol_angle_deg: float = 10.0,
    tol_dist_px: float = 25.0,
) -> list[list[int]]:
    """Snap each edge of the polygon to its closest compatible wall line.

    Algorithm:
        For each edge (p_i, p_{i+1}):
          - find the wall line with similar angle (within tol_angle_deg) and
            close enough to the edge midpoint (within tol_dist_px)
          - if none → keep the original edge as its own "target line"
        Reconstruct the polygon: each vertex = intersection of the two adjacent
        target lines (i-1 and i). If parallel, fall back to the original vertex.

    Args:
        polygon_xy: input polygon
        wall_lines: list of (x1,y1,x2,y2) from extract_wall_lines()
        tol_angle_deg: max angle deviation between edge and wall line
        tol_dist_px: max perpendicular distance edge-midpoint → wall line

    Returns:
        Snapped polygon (same length as input).
    """
    n = len(polygon_xy)
    if n < 3 or not wall_lines:
        return polygon_xy

    target_lines: list[tuple[float, float, float, float]] = []
    for i in range(n):
        p0 = polygon_xy[i]
        p1 = polygon_xy[(i + 1) % n]
        edge_angle = _angle_of_line(p0[0], p0[1], p1[0], p1[1])
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2

        best_line = None
        best_dist = tol_dist_px + 1
        for wx1, wy1, wx2, wy2 in wall_lines:
            w_angle = _angle_of_line(wx1, wy1, wx2, wy2)
            d_angle = abs(edge_angle - w_angle)
            d_angle = min(d_angle, 180.0 - d_angle)
            if d_angle > tol_angle_deg:
                continue
            d = _point_to_line_dist(mx, my, wx1, wy1, wx2, wy2)
            if d < best_dist:
                best_dist = d
                best_line = (float(wx1), float(wy1), float(wx2), float(wy2))

        if best_line is None:
            # Keep the original edge as its own target line
            best_line = (float(p0[0]), float(p0[1]),
                          float(p1[0]), float(p1[1]))
        target_lines.append(best_line)

    # Reconstruct vertices = intersection of adjacent target lines
    new_poly: list[list[int]] = []
    for i in range(n):
        prev_line = target_lines[(i - 1) % n]
        next_line = target_lines[i]
        v = _line_intersection(prev_line, next_line)
        if v is None:
            # Parallel target lines → fallback to original vertex
            v = (polygon_xy[i][0], polygon_xy[i][1])
        new_poly.append([int(round(v[0])), int(round(v[1]))])

    return new_poly


def postprocess_polygon(
    polygon_xy: list[list[int]],
    simplify_epsilon_pct: float = 1.0,
    axis_align_tolerance_deg: float | None = None,
    wall_lines: list[tuple[int, int, int, int]] | None = None,
    wall_snap_angle_deg: float = 10.0,
    wall_snap_dist_px: float = 25.0,
) -> list[list[int]]:
    """Full pipeline: simplify → optional axis-align → optional snap-to-walls.

    Snap-to-walls applied LAST: simplification gives us cleaner edges to map
    onto walls, and axis-align ensures the geometry is already orthogonal-ish
    before snapping.
    """
    out = simplify_dp(polygon_xy, simplify_epsilon_pct)
    if axis_align_tolerance_deg is not None and axis_align_tolerance_deg > 0:
        out = snap_axis_aligned(out, axis_align_tolerance_deg)
    if wall_lines:
        out = snap_polygon_to_walls(
            out, wall_lines,
            tol_angle_deg=wall_snap_angle_deg,
            tol_dist_px=wall_snap_dist_px,
        )
    return out
