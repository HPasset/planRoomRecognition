"""Specs de placement déclaratives par type de pièce. Pilote : chambre.

Une Rule = un équipement + une stratégie d'ancrage. Le résolveur place les
règles dans l'ordre ; les règles peuvent référencer un résultat précédent
par `rule_id` (ex : la RJ45 ancrée à la 1re prise).
"""
from __future__ import annotations
from dataclasses import dataclass

LEFT = "left"
RIGHT = "right"


@dataclass(frozen=True)
class Anchor:
    """Stratégie d'ancrage d'un équipement.

    kind :
      - "bed_side"     : côté `side` du lit, sur le mur tête-de-lit
      - "adjacent"     : accolé au résultat `ref` (autre règle)
      - "triangle"     : sur le mur d'en face, triangle avec `refs`
      - "beside_door"  : à côté de la porte, sur son mur
      - "centroid"     : barycentre de la pièce
    """
    kind: str
    side: str | None = None
    ref: str | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    equip_key: str
    anchor: Anchor


BEDROOM_SPEC: list[Rule] = [
    Rule("prise_1", "Prise",      Anchor(kind="bed_side", side=LEFT)),
    Rule("prise_2", "Prise",      Anchor(kind="bed_side", side=RIGHT)),
    Rule("rj45_1",  "RJ45",       Anchor(kind="adjacent", ref="prise_1")),
    Rule("prise_3", "Prise",      Anchor(kind="triangle", refs=("prise_1", "prise_2"))),
    Rule("switch_1", "Switch",    Anchor(kind="beside_door")),
    Rule("light_1", "LightPoint", Anchor(kind="centroid")),
]


SPEC_BY_ROOM_TYPE: dict[str, list[Rule]] = {
    "BedRoom": BEDROOM_SPEC,
}
