"""Résolveur : RoomContext + counts → équipements positionnés.

Place les règles de la spec dans l'ordre, en résolvant chaque ancre via les
primitives géométriques, puis applique la couche de raffinement (snap mur +
anti-collision). Marque `uncertain` quand une ancre repose sur une détection
absente ou quand le raffinement a dû déplacer un point au-delà du seuil.
"""
from __future__ import annotations

import math

from src.planrec.placement.contracts import Detection, RoomContext, PlacedEquipment
from src.planrec.placement.spec import SPEC_BY_ROOM_TYPE, Rule, LEFT
from src.planrec.placement import geometry as g

INSET = 15
MIN_GAP = 22
ACCOLE_GAP = 22
FLANK_GAP = 25          # décalage au-delà des extrémités du lit pour flanquer les chevets
SNAP_MAX = 20
UNCERTAIN_MOVE = 18


def _find(dets: list[Detection], classes: set[str]) -> Detection | None:
    """Détection de plus haute confiance parmi `classes` (None si aucune)."""
    cands = [d for d in dets if d.cls in classes]
    return max(cands, key=lambda d: d.confidence) if cands else None


def _distribute_on_perimeter(equip_key, n, edges, centroid, start_t):
    """Répartit `n` équipements hors-spec le long du périmètre (marqués incertains).

    Marche par pas irrationnel pour éviter les superpositions. Retourne
    (placements, next_t).
    """
    out = []
    t = start_t
    for _ in range(n):
        edge = edges[int(t * len(edges)) % len(edges)]
        px, py = g.point_on_edge(edge, (t * len(edges)) % 1.0, INSET, centroid)
        out.append(PlacedEquipment(equip_key=equip_key, x=px, y=py,
                                   confidence=0.5, uncertain=True,
                                   reason="hors spec : répartition mur libre"))
        t = (t + 0.21) % 1.0
    return out, t


def place_room(ctx: RoomContext, counts: dict[str, int]) -> list[PlacedEquipment]:
    spec = SPEC_BY_ROOM_TYPE.get(ctx.room_type)
    if spec is None:
        return []

    if len(ctx.polygon) < 3:
        return []
    area2 = 0.0
    n = len(ctx.polygon)
    for i in range(n):
        x0, y0 = ctx.polygon[i]
        x1, y1 = ctx.polygon[(i + 1) % n]
        area2 += x0 * y1 - x1 * y0
    if abs(area2) < 1.0:   # aire ~nulle → polygone dégénéré, on n'invente pas de positions
        return []

    bed = _find(ctx.furniture, {"Bed", "Double Bed", "Single Bed"})
    if bed is None:
        # Sans lit détecté, le moteur chambre n'a aucune valeur ajoutée (tout
        # son placement est relatif au lit). Il décline → l'appelant retombe
        # sur le placement périmétrique propre de la pièce (réparti sur les
        # murs + lumière au centre) plutôt que d'entasser une dégradation.
        return []

    edges = g.room_edges(ctx.polygon)
    centroid = g.polygon_centroid(ctx.polygon)
    door = _find(ctx.openings, {"door", "Door", "Single Door", "Double Door"})

    head_wall = g.bed_head_wall(bed.bbox, edges) if bed else None
    door_wall = g.edge_of(door.bbox, edges) if door else None

    # Lit « une place » en coin : un (ou deux) grand côté plaqué à un mur. Le
    # placement des chevets bascule alors sur le côté accessible (cf _resolve_rule).
    blocked_long = (g.bed_blocked_long_walls(bed.bbox, edges, head_wall)
                    if head_wall is not None else [])

    remaining = dict(counts)
    by_id: dict[str, PlacedEquipment] = {}
    rule_wall: dict[str, g.Edge] = {}   # rule_id → mur où la prise a été posée
    placed: list[PlacedEquipment] = []

    def take(equip_key: str) -> bool:
        if remaining.get(equip_key, 0) <= 0:
            return False
        remaining[equip_key] -= 1
        return True

    for rule in spec:
        if not take(rule.equip_key):
            continue
        x, y, uncertain, reason = _resolve_rule(
            rule, ctx, edges, centroid, bed, door, head_wall, door_wall, by_id,
            blocked_long, rule_wall,
        )
        pe = PlacedEquipment(equip_key=rule.equip_key, x=x, y=y,
                             confidence=0.9 if not uncertain else 0.5,
                             uncertain=uncertain, reason=reason)
        by_id[rule.rule_id] = pe
        placed.append(pe)

    # Équipements au-delà de ce que la spec consomme : répartis sur le périmètre.
    extra_t = 0.15
    for equip_key, n in remaining.items():
        if n <= 0:
            continue
        extras, extra_t = _distribute_on_perimeter(equip_key, n, edges, centroid, extra_t)
        placed.extend(extras)

    _refine(placed, ctx, centroid)
    return placed


def _resolve_rule(rule: Rule, ctx, edges, centroid, bed, door,
                  head_wall, door_wall, by_id, blocked_long, rule_wall):
    a = rule.anchor
    uncertain = False
    reason = ""

    if a.kind == "bed_side":
        if not (bed and head_wall is not None):
            t = 0.25 if a.side == LEFT else 0.75
            x, y = g.point_on_edge(edges[0], t, INSET, centroid)
            return x, y, True, "lit absent : prise répartie"

        if len(blocked_long) == 1:
            # Lit « une place » en coin : têtière (côté COURT) contre le mur
            # tête, un grand côté (côté LONG) contre `blocked_wall`. Placement
            # en L, le long des deux murs que touche le lit :
            #   - prise_1 (chevet tête, LEFT) → sur le MUR TÊTE, au-delà de
            #     l'extrémité du côté LIBRE (opposé au mur bloqué).
            #   - prise_2 (RIGHT) → dans la CONTINUITÉ du grand côté : sur
            #     `blocked_wall`, au-delà du PIED du lit (zone dégagée du mur).
            # Aucune prise ne tombe dans le coin coincé tête×côté bloqué.
            blocked_wall = blocked_long[0]
            if a.side == LEFT:
                wall, ref_mid = head_wall, blocked_wall.midpoint   # fuir le mur bloqué
                reason = "prise chevet tête, côté accessible (lit en coin)"
            else:
                wall, ref_mid = blocked_wall, head_wall.midpoint   # fuir le mur tête
                reason = "prise dans la continuité du grand côté, au-delà du pied (contre le mur)"
            t_lo, t_hi = g.project_extents(bed.bbox, wall)
            p_lo, p_hi = wall.point_at(t_lo), wall.point_at(t_hi)
            d_lo = math.hypot(p_lo[0] - ref_mid[0], p_lo[1] - ref_mid[1])
            d_hi = math.hypot(p_hi[0] - ref_mid[0], p_hi[1] - ref_mid[1])
            flank_dt = FLANK_GAP / (wall.length or 1.0)
            # on flanque AU-DELÀ de l'extrémité la plus éloignée de `ref_mid`
            t = (min(1.0, t_hi + flank_dt) if d_hi >= d_lo
                 else max(0.0, t_lo - flank_dt))
            x, y = g.point_on_edge(wall, t, INSET, centroid)
            rule_wall[rule.rule_id] = wall
            return x, y, False, reason

        if len(blocked_long) >= 2:
            # Alcôve : les deux grands côtés bloqués → repli sur le mur tête,
            # extrémité côté libre, marqué incertain.
            t_min, t_max = g.project_extents(bed.bbox, head_wall)
            flank_dt = FLANK_GAP / (head_wall.length or 1.0)
            t = max(0.0, t_min - flank_dt) if a.side == LEFT else min(1.0, t_max + flank_dt)
            x, y = g.point_on_edge(head_wall, t, INSET, centroid)
            rule_wall[rule.rule_id] = head_wall
            return x, y, True, "lit en alcôve (deux côtés bloqués) : placement approximatif"

        # Cas standard (lit accessible des deux côtés) : on flanque le lit JUSTE
        # AU-DELÀ de chaque extrémité (espace libre à côté), pas sur le coin du
        # lit. Sinon les deux prises se posent sur le matelas et la têtière
        # paraît n'en avoir qu'une (noyée dans le mobilier).
        t_min, t_max = g.project_extents(bed.bbox, head_wall)
        flank_dt = FLANK_GAP / (head_wall.length or 1.0)
        t = max(0.0, t_min - flank_dt) if a.side == LEFT else min(1.0, t_max + flank_dt)
        x, y = g.point_on_edge(head_wall, t, INSET, centroid)
        rule_wall[rule.rule_id] = head_wall
        reason = f"prise côté {a.side} du lit (au-delà de l'extrémité, contre le mur)"
        return x, y, False, reason

    if a.kind == "adjacent":
        ref = by_id.get(a.ref)
        if ref is not None:
            # Glisser le long du mur où la prise de réf a réellement été posée
            # (mur tête en standard, mur du côté libre en lit-en-coin). On
            # raisonne en paramètre `t` LE LONG du mur pour rester plaqué :
            # décaler la RJ45 d'ACCOLE_GAP côté EXTÉRIEUR du lit (pas sur le
            # matelas). Si ce côté déborde du segment (la prise est déjà à
            # l'extrémité du mur — cas lit flanqué juste au bout), on bascule de
            # l'autre côté : mieux vaut la RJ45 vers le lit MAIS plaquée au mur
            # que repoussée perpendiculairement dans la pièce (continuité du
            # lit au lieu du mur).
            ref_wall = rule_wall.get(a.ref, head_wall)
            if ref_wall is not None and bed is not None:
                L = ref_wall.length or 1.0
                dt = ACCOLE_GAP / L
                t_ref = g._project_t((ref.x, ref.y), ref_wall)
                bt_lo, bt_hi = g.project_extents(bed.bbox, ref_wall)
                bed_mid_t = (bt_lo + bt_hi) / 2.0
                away = dt if t_ref >= bed_mid_t else -dt   # s'éloigner du lit
                t_new = t_ref + away
                if not (0.0 <= t_new <= 1.0):              # déborde → repli
                    t_new = t_ref - away
                t_new = max(0.0, min(1.0, t_new))
                x, y = g.point_on_edge(ref_wall, t_new, INSET, centroid)
            else:
                x, y = ref.x + ACCOLE_GAP, ref.y
            return x, y, ref.uncertain, "RJ45 accolée à la prise (continuité mur)"
        x, y = g.point_on_edge(edges[0], 0.1, INSET, centroid)
        return x, y, True, "prise de référence absente"

    if a.kind == "triangle":
        p1 = by_id.get(a.refs[0])
        p2 = by_id.get(a.refs[1])
        if head_wall is not None and blocked_long and bed is not None:
            # Lit en coin : 3e prise sur le mur LIBRE d'en face (opposé au grand
            # côté bloqué), à l'aplomb du lit → triangle avec les 2 chevets.
            free_wall = g.opposite_edge(blocked_long[0], edges)
            bcx = (bed.bbox[0] + bed.bbox[2]) / 2.0
            bcy = (bed.bbox[1] + bed.bbox[3]) / 2.0
            t = max(0.0, min(1.0, g._project_t((int(bcx), int(bcy)), free_wall)))
            x, y = g.point_on_edge(free_wall, t, INSET, centroid)
            unc = bool((p1 and p1.uncertain) or (p2 and p2.uncertain))
            return x, y, unc, "3e prise mur libre d'en face (lit en coin)"
        if p1 and p2 and head_wall is not None:
            opp = g.opposite_edge(head_wall, edges)
            x, y = g.triangle_apex((p1.x, p1.y), (p2.x, p2.y), opp, INSET, centroid)
            return x, y, (p1.uncertain or p2.uncertain), "prise en triangle, mur d'en face"
        opp = g.opposite_edge(edges[0], edges)
        x, y = g.point_on_edge(opp, 0.5, INSET, centroid)
        return x, y, True, "triangle dégradé"

    if a.kind == "beside_door":
        if door and door_wall is not None:
            x, y = g.beside_door(door.bbox, door_wall, INSET, centroid)
            return x, y, True, "interrupteur côté dégagé porte (sens d'ouverture inconnu, à vérifier)"
        x, y = g.point_on_edge(edges[0], 0.5, INSET, centroid)
        return x, y, True, "porte absente : interrupteur approximatif"

    if a.kind == "centroid":
        return centroid[0], centroid[1], False, "point lumineux central"

    return centroid[0], centroid[1], True, "ancre inconnue"


def _refine(placed: list[PlacedEquipment], ctx: RoomContext, centroid) -> None:
    """Snap mur (sauf point lumineux) puis anti-collision. Mute en place."""
    # Ordre : snap-to-wall AVANT resolve_collisions, et PAS ré-appliqué ensuite.
    # L'étalement anti-collision peut donc décaler légèrement un point hors du
    # mur. Acceptable pour le pilote (ctx.wall_lines est vide → snap no-op) ;
    # un re-snap post-collision est un raffinement futur.
    for pe in placed:
        if pe.equip_key == "LightPoint":
            continue
        (nx, ny), moved = g.snap_to_wall(
            (pe.x, pe.y), ctx.wall_lines, SNAP_MAX, INSET, centroid,
        )
        pe.x, pe.y = nx, ny
        if moved > UNCERTAIN_MOVE:
            pe.uncertain = True

    movable = [pe for pe in placed if pe.equip_key != "LightPoint"]
    pts = g.resolve_collisions([(pe.x, pe.y) for pe in movable], MIN_GAP)
    for pe, (x, y) in zip(movable, pts):
        pe.x, pe.y = x, y
