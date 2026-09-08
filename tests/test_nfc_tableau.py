"""Tests pour le module nfc_tableau (algo greedy de répartition tableau électrique)."""
from __future__ import annotations
import pytest

from src.planrec.nfc_tableau import CircuitType, Circuit


def test_circuit_type_values():
    """Types de circuits couverts (V1 + v2 : prises cuisine, VMC, PAC, borne)."""
    expected = {"lighting", "socket", "kitchen_special", "laundry",
                "boiler", "heating", "towel_warmer",
                "kitchen_socket", "vmc", "heat_pump", "ev_charger"}
    actual = {ct.value for ct in CircuitType}
    assert actual == expected


def test_circuit_dataclass_fields():
    """Circuit a id, type, label, breaker_amps, cable_section_mm2, rooms_served,
    n_devices, requires_type_a."""
    c = Circuit(
        id="circ_abc12345",
        type=CircuitType.LIGHTING,
        label="Lum Séjour",
        breaker_amps=10,
        cable_section_mm2=1.5,
        rooms_served=["Sejour"],
        n_devices=3,
        requires_type_a=False,
    )
    assert c.id == "circ_abc12345"
    assert c.type == CircuitType.LIGHTING
    assert c.breaker_amps == 10
    assert c.cable_section_mm2 == 1.5
    assert not c.requires_type_a


def test_rcd_dataclass_fields():
    from src.planrec.nfc_tableau import RCD, Circuit, CircuitType
    c = Circuit(id="c1", type=CircuitType.LIGHTING, label="x",
                breaker_amps=10, cable_section_mm2=1.5)
    rcd = RCD(id="rcd_1", rcd_type="A", amps=40, sensitivity_ma=30,
              circuits=[c])
    assert rcd.rcd_type == "A"
    assert rcd.amps == 40
    assert rcd.sensitivity_ma == 30
    assert len(rcd.circuits) == 1


def test_tableau_dataclass_fields():
    from src.planrec.nfc_tableau import Tableau
    t = Tableau(
        typology="T3", typology_source="auto", surface_m2=80.0,
        heating_enabled=True, rcds=[], total_modules=0, n_rails=1,
        notes=["RJ45 → coffret VDI"], warnings=[],
    )
    assert t.typology == "T3"
    assert t.heating_enabled is True
    assert t.notes == ["RJ45 → coffret VDI"]


def test_detect_typology_T1_studio():
    """1 séjour seul → T1 (studio)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global(
        [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}],
    )
    assert detect_typology(devis) == "T1"


def test_detect_typology_T2_living_plus_1_bedroom():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T2"


def test_detect_typology_T3_living_plus_2_bedrooms():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T3"


def test_detect_typology_T5_capped_at_5():
    """4+ chambres + séjour → T5 (on cap au lieu de T6/T7)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "B4", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T5"


def test_lighting_one_room_one_circuit_if_few_lights():
    """Une pièce avec ≤5 lights → 1 circuit éclairage 10A/1.5mm²."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    rooms_with_lights = [("Sejour", 3), ("Chambre 1", 2)]
    circuits = _build_lighting_circuits(rooms_with_lights)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 10
    assert circuits[0].cable_section_mm2 == 1.5
    assert circuits[0].n_devices == 5
    assert set(circuits[0].rooms_served) == {"Sejour", "Chambre 1"}


def test_lighting_big_room_keeps_one_dedicated_circuit():
    """Pièce > 5 lights (salon 6 spots + 1 PL) → 1 circuit dédié entier, pas
    de découpage (règle cabinet 2026-09-07). Les autres pièces sont packées
    à part."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    circuits = _build_lighting_circuits([("Sejour", 7), ("WC", 1), ("Chambre 1", 1)])
    assert len(circuits) == 2
    big = next(c for c in circuits if c.rooms_served == ["Sejour"])
    assert big.n_devices == 7
    assert sorted(c.n_devices for c in circuits) == [2, 7]


def test_lighting_label_uses_room_codes():
    """Label = préfixe court + codes pièces (lisible sur l'étiquette)."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    codes = {"Chambre 2": "CH2", "Chambre 3": "CH3", "Dégagement": "DGT"}
    circuits = _build_lighting_circuits(
        [("Chambre 2", 1), ("Chambre 3", 1), ("Dégagement", 1)], codes=codes)
    assert len(circuits) == 1
    assert circuits[0].label == "Écl. CH2 CH3 DGT (×3)"
    assert circuits[0].rooms_served == ["Chambre 2", "Chambre 3", "Dégagement"]


def test_sockets_one_room_one_circuit():
    """Pièce 5 prises → 1 circuit 16A/1.5mm² (NFC : 5 prises max)."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms_with_sockets = [("Sejour", 5)]
    circuits = _build_socket_circuits(rooms_with_sockets)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 16
    assert circuits[0].cable_section_mm2 == 1.5
    assert circuits[0].n_devices == 5


def test_sockets_pack_small_rooms_together():
    """3 petites pièces (2+1+1 prises) → 1 circuit grouppé."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("WC", 1), ("Entrée", 2), ("Couloir", 1)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 1
    assert circuits[0].n_devices == 4


def test_sockets_large_room_split_by_eight():
    """Pièce 12 prises → découpée en circuits de 8 max : 8 + 4."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("Sejour", 12)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 2
    assert sorted(c.n_devices for c in circuits) == [4, 8]
    assert all(c.breaker_amps == 16 and c.cable_section_mm2 == 1.5
               for c in circuits)


def test_heating_pack_2_convectors_per_circuit():
    """4 convecteurs → 2 circuits HEATING (2 max par circuit, 20A)."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    rooms_with_conv = [("Sejour", 1), ("Chambre 1", 1), ("Chambre 2", 1),
                       ("Chambre 3", 1)]
    circuits = _build_heating_circuits(rooms_with_conv, towel_warmer_rooms=[])
    heating = [c for c in circuits if c.type.value == "heating"]
    assert len(heating) == 2
    assert all(c.breaker_amps == 20 and c.cable_section_mm2 == 2.5
               for c in heating)
    assert sum(c.n_devices for c in heating) == 4


def test_heating_1_circuit_per_towel_warmer():
    """3 sèche-serviettes → 3 circuits dédiés TOWEL_WARMER (1 par circuit),
    chaque circuit garde la SDB d'origine dans rooms_served."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits(
        rooms_with_convectors=[],
        towel_warmer_rooms=["SDB 1", "SDB 2", "SDB 3"],
    )
    tw = [c for c in circuits if c.type.value == "towel_warmer"]
    assert len(tw) == 3
    assert [c.rooms_served for c in tw] == [["SDB 1"], ["SDB 2"], ["SDB 3"]]


def test_heating_single_towel_warmer_keeps_room():
    """1 sèche-serviettes → label sans index + rooms_served=[sdb]."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits([], towel_warmer_rooms=["SDB"])
    tw = [c for c in circuits if c.type.value == "towel_warmer"]
    assert len(tw) == 1
    assert tw[0].rooms_served == ["SDB"]
    assert tw[0].label == "Sèche-serviettes"


def test_heating_empty_lists():
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits([], towel_warmer_rooms=[])
    assert circuits == []


def test_specialized_each_appliance_one_circuit():
    """6 appareils spé → 6 circuits dédiés, room d'origine conservée."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    rooms_by_type = {
        EquipmentType.OVEN: ["Cuisine"],
        EquipmentType.COOKTOP: ["Cuisine"],
        EquipmentType.DISHWASHER: ["Cuisine"],
        EquipmentType.WASHING_MACHINE: ["Cellier"],
        EquipmentType.DRYER: ["Cellier"],
        EquipmentType.BOILER: ["Cellier"],
    }
    circuits = _build_specialized_circuits(rooms_by_type)
    assert len(circuits) == 6
    # Toutes les pièces d'origine sont préservées dans rooms_served
    rooms_seen = [c.rooms_served[0] for c in circuits]
    assert rooms_seen.count("Cuisine") == 3
    assert rooms_seen.count("Cellier") == 3


def test_specialized_plaque_is_32A_6mm2_type_a():
    """Plaque cuisson → calibre 32A, câble 6mm², requires_type_a=True."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    rooms_by_type = {EquipmentType.COOKTOP: ["Cuisine"]}
    circuits = _build_specialized_circuits(rooms_by_type)
    assert len(circuits) == 1
    plaque = circuits[0]
    assert plaque.breaker_amps == 32
    assert plaque.cable_section_mm2 == 6.0
    assert plaque.requires_type_a is True
    assert plaque.rooms_served == ["Cuisine"]


def test_specialized_lavelinge_is_20A_2_5mm2_type_a():
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    rooms_by_type = {EquipmentType.WASHING_MACHINE: ["Cellier"]}
    circuits = _build_specialized_circuits(rooms_by_type)
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].requires_type_a is True
    assert circuits[0].rooms_served == ["Cellier"]


def test_min_rcds_T2_returns_2():
    """T2 → 2 RCD minimum (règle cabinet)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=None,
                             n_breakers=5) == 2


def test_min_rcds_surface_overrides_typology():
    """T1 mais 120 m² → 3 RCD (règle NFC stricte > règle typo)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T1", surface_m2=120.0,
                             n_breakers=5) == 3


def test_min_rcds_many_breakers_forces_more():
    """T2 (2 RCD min) mais 18 disjoncteurs → ceil(18/8) = 3 RCD."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=80.0,
                             n_breakers=18) == 3


def test_distribute_type_A_contains_cooktop_and_lavelinge():
    """RCD1 Type A contient OBLIGATOIREMENT Plaque + LL."""
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Plaque",
                     breaker_amps=32, cable_section_mm2=6.0,
                     requires_type_a=True)
    ll = Circuit(id="c2", type=CircuitType.LAUNDRY, label="LL",
                 breaker_amps=20, cable_section_mm2=2.5,
                 requires_type_a=True)
    other = Circuit(id="c3", type=CircuitType.LIGHTING, label="Lum",
                    breaker_amps=10, cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([plaque, ll, other], n_rcds=2)
    assert rcds[0].rcd_type == "A"
    type_a_ids = {c.id for c in rcds[0].circuits}
    assert "c1" in type_a_ids
    assert "c2" in type_a_ids


def test_distribute_other_rcds_are_type_AC():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="P",
                     breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True)
    others = [Circuit(id=f"c{i+2}", type=CircuitType.LIGHTING, label=f"L{i}",
                      breaker_amps=10, cable_section_mm2=1.5)
              for i in range(2)]
    rcds = _distribute_circuits_to_rcds([plaque] + others, n_rcds=2)
    assert rcds[0].rcd_type == "A"
    assert rcds[1].rcd_type == "AC"


def test_rcd_amps_formula_normalized():
    """RCD avec 4× 20A non-chauffage → (4*20)/2 = 40A normalisé."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id=f"c{i}", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5)
        for i in range(4)
    ]
    assert _compute_rcd_amps(circuits) == 40


def test_rcd_amps_heating_summed_not_halved():
    """1× 20A socket + 1× 20A heating → 20/2 + 20 = 30 → arrondi à 40A."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id="c1", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
        Circuit(id="c2", type=CircuitType.HEATING, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
    ]
    assert _compute_rcd_amps(circuits) == 40


def test_generate_tableau_T3_complete_flow():
    """T3 standard (séjour + 2 chambres + cuisine + SdB + entrée) →
    tableau cohérent : 3 RCD min, Type A contient Plaque + LL, notes RJ45."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "E1", "c2_class": "Entry"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)

    assert tableau.typology == "T3"
    assert tableau.heating_enabled is True
    assert len(tableau.rcds) >= 3
    # Premier RCD est Type A et contient Plaque + LL
    type_a_rcd = tableau.rcds[0]
    assert type_a_rcd.rcd_type == "A"
    labels = [c.label for c in type_a_rcd.circuits]
    assert any("Plaque" in lbl for lbl in labels)
    assert any("Lave-linge" in lbl for lbl in labels)
    # Note RJ45 hors tableau
    assert any("RJ45" in n for n in tableau.notes)


def test_generate_tableau_propagates_rooms_to_specialized_and_towel_circuits():
    """rooms_served est rempli pour tous les circuits spé (Four/Plaque/LV en
    Cuisine, LL/SL/Chaudière en Cellier) et pour chaque sèche-serviettes (SDB)."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "C1", "c2_class": "Storage"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "S2", "c2_class": "Bath"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)

    all_circuits = [c for rcd in tableau.rcds for c in rcd.circuits]
    by_label_prefix = lambda prefix: [
        c for c in all_circuits if c.label.startswith(prefix)
    ]
    # Cuisine
    for prefix in ("Four", "Plaque cuisson", "Lave-vaisselle"):
        matches = by_label_prefix(prefix)
        assert matches, f"circuit {prefix} manquant"
        for c in matches:
            assert c.rooms_served == ["Cuisine"], (
                f"{prefix}: rooms_served={c.rooms_served}"
            )
    # Cellier
    for prefix in ("Lave-linge", "Sèche-linge", "Cumulus (ECS)"):
        matches = by_label_prefix(prefix)
        assert matches, f"circuit {prefix} manquant"
        for c in matches:
            assert c.rooms_served == ["CellierBuanderie"], (
                f"{prefix}: rooms_served={c.rooms_served}"
            )
    # Sèche-serviettes : 1 par SDB, room indexée propagée
    tw = [c for c in all_circuits if c.type.value == "towel_warmer"]
    assert len(tw) == 2
    rooms_seen = sorted(c.rooms_served[0] for c in tw)
    assert rooms_seen == ["SalleDeBain 1", "SalleDeBain 2"]


def test_generate_tableau_room_labels_overrides_cat_seen_indexing():
    """room_labels permet de préserver les labels pastille même après
    suppression d'une pièce intermédiaire — sinon cat_seen ré-indexerait
    ('Chambre 3' → 'Chambre 2' après drag-out de 'Chambre 2'), ce qui
    déroute l'utilisateur."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    # Simule l'état post-drag-out de Chambre 2 : il reste Chambre 1 et
    # Chambre 3 (room_id = pastille_id réel).
    rooms = [
        {"id": "pid_c1", "c2_class": "BedRoom"},
        {"id": "pid_c3", "c2_class": "BedRoom"},
        {"id": "pid_k1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    room_labels = {
        "pid_c1": "Chambre 1",
        "pid_c3": "Chambre 3",
        "pid_k1": "Cuisine",
    }
    tableau = generate_tableau(
        devis_global=devis, heating_enabled=True, room_labels=room_labels,
    )

    all_rooms = set()
    for rcd in tableau.rcds:
        for c in rcd.circuits:
            all_rooms.update(c.rooms_served)
    # Labels d'origine préservés
    assert "Chambre 3" in all_rooms
    # AUCUN circuit ne doit afficher "Chambre 2" — il n'existe plus
    assert "Chambre 2" not in all_rooms


def test_generate_tableau_falls_back_to_cat_seen_when_no_label():
    """Si room_labels n'a pas un room_id donné, fallback sur cat_seen
    (compat ascendante avec les call sites qui ne passent pas room_labels)."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "r1", "c2_class": "BedRoom"},
        {"id": "r2", "c2_class": "BedRoom"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    # room_labels vide → cat_seen prend le relais
    tableau = generate_tableau(
        devis_global=devis, heating_enabled=True, room_labels={},
    )
    all_rooms = set()
    for rcd in tableau.rcds:
        for c in rcd.circuits:
            all_rooms.update(c.rooms_served)
    assert "Chambre 1" in all_rooms
    assert "Chambre 2" in all_rooms


def test_generate_tableau_typology_override():
    """typology_override force la typologie quel que soit le devis."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ]
    devis = compute_devis_global(rooms)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True,
                                typology_override="T4")
    assert tableau.typology == "T4"
    assert tableau.typology_source == "user_override"


def test_generate_tableau_heating_disabled_no_heating_circuits():
    """heating_enabled=False → 0 circuits HEATING ni TOWEL_WARMER."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "S1", "c2_class": "Bath"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    all_circuits = [c for r in tableau.rcds for c in r.circuits]
    heating_circuits = [c for c in all_circuits
                        if c.type.value in ("heating", "towel_warmer")]
    assert heating_circuits == []


def test_edge_case_T1_studio_one_rcd_type_A():
    """T1 studio (séjour seul + cuisine + SdB) → 1 RCD Type A unique contenant
    Plaque + LL + tout le reste."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)
    assert tableau.typology == "T1"
    assert len(tableau.rcds) >= 1
    assert tableau.rcds[0].rcd_type == "A"


def test_edge_case_minimal_logement_no_laundry_circuit():
    """Logement minimal (séjour seul) : aucune pièce candidate au lave-linge
    garanti → pas de circuit LAUNDRY. Les seuls circuits Type A sont l'éclairage
    (v2 : éclairage en Type A ; pas de lave-linge fantôme — 2026-06-17)."""
    from src.planrec.nfc_tableau import generate_tableau, CircuitType
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0}]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    circuits = [c for r in tableau.rcds for c in r.circuits]
    assert not any(c.type == CircuitType.LAUNDRY for c in circuits)
    type_a_rcd = next(r for r in tableau.rcds if r.rcd_type == "A")
    types = sorted(c.type for c in type_a_rcd.circuits)
    assert types == [CircuitType.LIGHTING, CircuitType.SOCKET]  # 1 éclairage + GTL


# --- v2 : différentiels A/F/AC, prises cuisine, VMC/PAC/borne ---

@pytest.fixture
def simple_kitchen_devis():
    from src.planrec.nfc_rules import compute_devis_global
    return compute_devis_global([{"id": "K1", "c2_class": "Kitchen"}],
                                heating_enabled=False)


def test_circuit_has_type_f_flag_default_false():
    from src.planrec.nfc_tableau import Circuit, CircuitType
    c = Circuit(id="c1", type=CircuitType.SOCKET, label="x", breaker_amps=16,
                cable_section_mm2=1.5)
    assert c.requires_type_f is False


def test_new_circuit_types_v2_exist():
    from src.planrec.nfc_tableau import CircuitType
    assert CircuitType.KITCHEN_SOCKET.value == "kitchen_socket"
    assert CircuitType.VMC.value == "vmc"
    assert CircuitType.HEAT_PUMP.value == "heat_pump"
    assert CircuitType.EV_CHARGER.value == "ev_charger"


def test_lighting_circuits_not_flagged_type_a():
    """Un seul éclairage va sur le type A (choisi à la répartition), les
    circuits éclairage ne sont donc plus tous flaggés type A (2026-09-07)."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    circuits = _build_lighting_circuits([("Sejour", 3)])
    assert circuits and not any(c.requires_type_a for c in circuits)


def test_kitchen_sockets_dedicated_20a():
    from src.planrec.nfc_tableau import _build_kitchen_socket_circuits, CircuitType
    circuits = _build_kitchen_socket_circuits([("Cuisine", 6)])
    assert len(circuits) == 1
    assert circuits[0].type == CircuitType.KITCHEN_SOCKET
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].n_devices == 6
    # label sans répétition de "cuisine" + quantité (la pièce est dans rooms_served)
    assert circuits[0].label == "PC Cuisine (×6)"
    assert circuits[0].rooms_served == ["Cuisine"]


def test_generate_tableau_kitchen_sockets_separate(simple_kitchen_devis):
    from src.planrec.nfc_tableau import generate_tableau, CircuitType
    tableau = generate_tableau(devis_global=simple_kitchen_devis, heating_enabled=False)
    circuits = [c for r in tableau.rcds for c in r.circuits]
    ksock = [c for c in circuits if c.type == CircuitType.KITCHEN_SOCKET]
    assert len(ksock) == 1 and ksock[0].breaker_amps == 20
    # aucune prise cuisine sur un circuit SOCKET 16A
    gen_sock = [c for c in circuits if c.type == CircuitType.SOCKET]
    assert all(c.breaker_amps == 16 for c in gen_sock)


def test_specialized_vmc_pac_ev_specs():
    from src.planrec.nfc_tableau import _build_specialized_circuits, CircuitType
    from src.planrec.nfc_rules import EquipmentType
    out = _build_specialized_circuits({
        EquipmentType.VMC: ["Cellier"],
        EquipmentType.HEAT_PUMP: ["Sejour"],
        EquipmentType.EV_CHARGER: ["Garage"],
    })
    by_type = {c.type: c for c in out}
    vmc = by_type[CircuitType.VMC]
    assert (vmc.breaker_amps, vmc.cable_section_mm2) == (16, 1.5)
    assert vmc.requires_type_a and not vmc.requires_type_f
    pac = by_type[CircuitType.HEAT_PUMP]
    assert (pac.breaker_amps, pac.cable_section_mm2) == (32, 6.0)
    assert pac.requires_type_f and not pac.requires_type_a
    ev = by_type[CircuitType.EV_CHARGER]
    assert (ev.breaker_amps, ev.cable_section_mm2) == (32, 6.0)
    assert ev.requires_type_f


def test_rcd_amps_counts_heat_pump_as_heating():
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    pac = Circuit(id="p", type=CircuitType.HEAT_PUMP, label="PAC",
                  breaker_amps=32, cable_section_mm2=6.0, requires_type_f=True)
    assert _compute_rcd_amps([pac]) == 40


def test_distribute_groups_by_differential_type():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    light = Circuit(id="l", type=CircuitType.LIGHTING, label="Ecl", breaker_amps=10,
                    cable_section_mm2=1.5, requires_type_a=True)
    plaque = Circuit(id="p", type=CircuitType.KITCHEN_SPECIAL, label="Plaque",
                     breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True)
    ev = Circuit(id="e", type=CircuitType.EV_CHARGER, label="Borne", breaker_amps=32,
                 cable_section_mm2=6.0, requires_type_f=True)
    sock = Circuit(id="s", type=CircuitType.SOCKET, label="Prises", breaker_amps=16,
                   cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([light, plaque, ev, sock], n_rcds=2)
    a = [r for r in rcds if r.rcd_type == "A"]
    f = [r for r in rcds if r.rcd_type == "F"]
    ac = [r for r in rcds if r.rcd_type == "AC"]
    assert a and all(c.requires_type_a for r in a for c in r.circuits)
    assert f and all(c.requires_type_f for r in f for c in r.circuits)
    assert ac and all(not c.requires_type_a and not c.requires_type_f
                      for r in ac for c in r.circuits)


def test_distribute_no_type_f_when_absent():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    light = Circuit(id="l", type=CircuitType.LIGHTING, label="Ecl", breaker_amps=10,
                    cable_section_mm2=1.5, requires_type_a=True)
    sock = Circuit(id="s", type=CircuitType.SOCKET, label="P", breaker_amps=16,
                   cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([light, sock], n_rcds=2)
    assert not any(r.rcd_type == "F" for r in rcds)
    assert any(r.rcd_type == "A" for r in rcds)


def test_distribute_splits_group_over_eight():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    circuits = [Circuit(id=f"l{i}", type=CircuitType.LIGHTING, label="E",
                        breaker_amps=10, cable_section_mm2=1.5, requires_type_a=True)
                for i in range(10)]
    rcds = _distribute_circuits_to_rcds(circuits, n_rcds=1)
    a = [r for r in rcds if r.rcd_type == "A"]
    assert len(a) == 2 and all(len(r.circuits) <= 8 for r in a)


# --- 2026-09-07 : plafond 63 A, prises GTL, un seul éclairage type A, codes ---

def _circ(i, ctype, amps, **kw):
    from src.planrec.nfc_tableau import Circuit
    return Circuit(id=f"c{i}", type=ctype, label="x", breaker_amps=amps,
                   cable_section_mm2=2.5, **kw)


def test_distribute_caps_rcd_at_63A():
    """6 convecteurs 20A comptés plein pot = 120 A → impossible sur un seul
    ID : découpé en ID ≤ 63 A chacun."""
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, CircuitType
    circuits = [_circ(i, CircuitType.HEATING, 20) for i in range(6)]
    rcds = _distribute_circuits_to_rcds(circuits, n_rcds=1)
    assert all(r.amps <= 63 for r in rcds)
    assert sum(len(r.circuits) for r in rcds) == 6
    assert len(rcds) == 2


def test_distribute_one_lighting_on_type_a_rest_spread_on_ac():
    """Un seul éclairage sur l'ID type A ; les autres éclairages vont un par
    ID AC avant tout autre circuit."""
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, CircuitType
    lights = [_circ(i, CircuitType.LIGHTING, 10) for i in range(3)]
    plaque = _circ(10, CircuitType.KITCHEN_SPECIAL, 32, requires_type_a=True)
    socks = [_circ(20 + i, CircuitType.SOCKET, 16) for i in range(4)]
    rcds = _distribute_circuits_to_rcds(lights + [plaque] + socks, n_rcds=3)
    a = [r for r in rcds if r.rcd_type == "A"]
    ac = [r for r in rcds if r.rcd_type == "AC"]
    assert len(a) == 1
    assert sum(1 for c in a[0].circuits if c.type == CircuitType.LIGHTING) == 1
    assert len(ac) == 2
    assert all(sum(1 for c in r.circuits if c.type == CircuitType.LIGHTING) == 1
               for r in ac)


def test_generate_tableau_adds_gtl_sockets_on_type_a():
    """PC GTL (×2) : toujours présentes, 16 A, sur l'ID type A."""
    from src.planrec.nfc_tableau import generate_tableau, CircuitType
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([{"id": "L1", "c2_class": "LivingRoom"}],
                                 heating_enabled=False)
    tableau = generate_tableau(devis, heating_enabled=False)
    gtl = [c for r in tableau.rcds for c in r.circuits if c.label == "PC GTL (×2)"]
    assert len(gtl) == 1
    assert (gtl[0].type, gtl[0].breaker_amps, gtl[0].n_devices) == (CircuitType.SOCKET, 16, 2)
    assert gtl[0].requires_type_a
    rcd = next(r for r in tableau.rcds if gtl[0] in r.circuits)
    assert rcd.rcd_type == "A"


def test_generate_tableau_room_codes_and_bureau():
    """Codes pièces : catégorie + index si plusieurs ; « Bureau » → BUR."""
    from src.planrec.nfc_tableau import generate_tableau, CircuitType
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom"},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "E1", "c2_class": "Entry"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "T1", "c2_class": "Storage"},
    ], heating_enabled=False)
    labels = {"B1": "Chambre principale", "B2": "Chambre 2", "B3": "Bureau",
              "E1": "Dégagement", "S1": "Salle de bain", "T1": "Cellier"}
    tableau = generate_tableau(devis, heating_enabled=False, room_labels=labels)
    lights = [c for r in tableau.rcds for c in r.circuits if c.type == CircuitType.LIGHTING]
    all_labels = " ".join(c.label for c in lights)
    for code in ("SEJ", "CH1", "CH2", "BUR", "DGT", "BAIN", "CEL"):
        assert code in all_labels, (code, all_labels)
    assert all(c.label.startswith("Écl. ") and c.label.endswith(f"(×{c.n_devices})") for c in lights)
    assert any(c.rooms_served == ["Bureau"] or "Bureau" in c.rooms_served for c in lights)


def test_generate_tableau_T4_all_rcds_under_63A():
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global
    rooms = [{"id": "L", "c2_class": "LivingRoom", "surface_m2": 40},
             {"id": "K", "c2_class": "Kitchen"}, {"id": "S", "c2_class": "Bath"},
             {"id": "T", "c2_class": "Storage"}, {"id": "E", "c2_class": "Entry"},
             {"id": "G", "c2_class": "Garage"}, {"id": "O", "c2_class": "Outdoor"}]
    rooms += [{"id": f"B{i}", "c2_class": "BedRoom", "surface_m2": 12} for i in range(4)]
    tableau = generate_tableau(compute_devis_global(rooms, heating_enabled=True))
    assert all(r.amps <= 63 for r in tableau.rcds)
    assert all(len(r.circuits) <= 8 for r in tableau.rcds)


def test_sockets_big_room_remainder_packed_with_small_rooms():
    """Salon 10 prises + 2 chambres de 3 → 8 dédiées au salon, puis 2 + 3 + 3
    sur un même circuit (le reliquat retourne dans le pool)."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    circuits = _build_socket_circuits([("Sejour", 10), ("Chambre 1", 3), ("Chambre 2", 3)])
    assert sorted(c.n_devices for c in circuits) == [8, 8]
    mixed = next(c for c in circuits if len(c.rooms_served) > 1)
    assert set(mixed.rooms_served) == {"Sejour", "Chambre 1", "Chambre 2"}
