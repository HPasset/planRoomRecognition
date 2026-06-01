"""
DWG/DXF analysis pipeline.

Lit les fichiers DWG (via conversion ODA → DXF) ou DXF (directement) déposés
dans `data/raw/plans_dwg/`, parse leur structure (layers, entités), tente une
classification heuristique (murs/portes/pièces) et rend le tout en PNG.

Sortie pour chaque plan :
- report.json    : stats layers + entités + classification heuristique
- raster.png     : rendu haute déf depuis le DXF
- overlay_walls.png  : murs en rouge
- overlay_doors.png  : portes en vert
- annotations.geojson : entités classifiées au format GeoJSON

Run :
    .venv/bin/python experiments/dwg_pipeline/run_analysis.py
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import ezdxf


class StepTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise StepTimeout("step exceeded timeout")


def with_timeout(seconds: int):
    """Context manager : timeout via SIGALRM (POSIX uniquement)."""
    class _Guard:
        def __enter__(self):
            self._prev = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(seconds)
            return self
        def __exit__(self, *exc):
            signal.alarm(0)
            signal.signal(signal.SIGALRM, self._prev)
            return False
    return _Guard()
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection, LineCollection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DWG_DIR = PROJECT_ROOT / "data" / "raw" / "plans_dwg"
DEFAULT_DXF_DIR = PROJECT_ROOT / "data" / "raw" / "plans_dxf"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "dwg_pipeline" / "outputs"

ODA_PATH = "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

# Heuristiques de nommage de layers — FR + EN (US AIA) + ES
WALL_LAYER_PATTERNS = [
    # FR
    r"mur", r"cloison", r"porteur", r"struct",
    # EN (AIA standard : A-WALL, A-WALL-FULL, S-WALL-...)
    r"wall", r"a-?wall", r"s-?wall", r"^m[\-_]",
    # ES
    r"muro", r"pared", r"tabique",
    r"partition", r"prtn",
]
DOOR_LAYER_PATTERNS = [
    r"porte", r"door", r"a-?door",
    r"puerta",  # ES
    r"^pf[\-_\d]", r"^p[\-_]",
]
WINDOW_LAYER_PATTERNS = [
    r"fenetre", r"fen[\-_]", r"window", r"baie", r"a-?glaz",
    r"ventana",  # ES
]
ROOM_LAYER_PATTERNS = [
    r"piece", r"room", r"surface", r"sh[\-_]", r"a-?area",
    r"habitacion", r"habitaciones", r"estancia",  # ES
]
FURNITURE_LAYER_PATTERNS = [
    r"mobilier", r"meuble", r"furn", r"equip",
    r"mobiliario", r"muebles",  # ES
    r"cocina", r"baño", r"bath",  # cuisine/bain en ES/EN
]
DIMENSION_LAYER_PATTERNS = [
    r"cote", r"dim", r"text", r"annot",
    r"cotas",  # ES
    r"^defpoints$",  # AutoCAD default
    r"sheet", r"marco", r"tarjeta",  # layout/cartouche
]


def match_any(name: str, patterns: list[str]) -> bool:
    name_low = name.lower()
    return any(re.search(p, name_low) for p in patterns)


def classify_layer(name: str) -> str:
    """Classifie un nom de layer en catégorie sémantique."""
    if match_any(name, WALL_LAYER_PATTERNS):
        return "wall"
    if match_any(name, DOOR_LAYER_PATTERNS):
        return "door"
    if match_any(name, WINDOW_LAYER_PATTERNS):
        return "window"
    if match_any(name, ROOM_LAYER_PATTERNS):
        return "room"
    if match_any(name, FURNITURE_LAYER_PATTERNS):
        return "furniture"
    if match_any(name, DIMENSION_LAYER_PATTERNS):
        return "dimension"
    return "unknown"


def has_oda() -> bool:
    return Path(ODA_PATH).exists()


def convert_dwg_to_dxf(dwg_path: Path, output_dir: Path) -> Path | None:
    """Convertit un .dwg en .dxf via ODA File Converter.

    ODA File Converter syntax (CLI mode) :
        ODAFileConverter <input_dir> <output_dir> <out_ver> <out_format>
                         <recurse> <audit> [filter]
    où :
        out_ver    = "ACAD2018" (ou autre version)
        out_format = "DXF"
        recurse    = "0" ou "1"
        audit      = "0" ou "1"
        filter     = "*.DWG" (optionnel)

    Le converter traite tout un dossier, pas un seul fichier. On copie le DWG
    dans un dossier temporaire, on convertit, on récupère le DXF.
    """
    if not has_oda():
        print(f"  ! ODA File Converter introuvable à {ODA_PATH}")
        print("    Téléchargez-le sur https://www.opendesign.com/guestfiles/oda_file_converter")
        return None

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_in:
        tmp_in_path = Path(tmp_in)
        shutil.copy2(dwg_path, tmp_in_path / dwg_path.name)
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            ODA_PATH,
            str(tmp_in_path),
            str(output_dir),
            "ACAD2018",   # output AutoCAD version
            "DXF",        # output format
            "0",          # no recurse
            "1",          # audit
            "*.DWG",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                print(f"  ! ODA conversion failed (rc={result.returncode})")
                if result.stderr:
                    print(f"    stderr: {result.stderr[:300]}")
                return None
        except subprocess.TimeoutExpired:
            print(f"  ! ODA conversion timed out (>120s)")
            return None

        expected = output_dir / (dwg_path.stem + ".dxf")
        if expected.exists():
            return expected
        # ODA may produce a different casing
        for candidate in output_dir.glob(f"{dwg_path.stem}*.dxf"):
            return candidate
        print(f"  ! ODA conversion done but DXF non trouvé dans {output_dir}")
        return None


def parse_dxf(dxf_path: Path) -> dict:
    """Lit un DXF avec ezdxf et retourne un rapport structuré."""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    # Stats par layer
    layers_info: dict[str, dict] = {}
    for layer in doc.layers:
        name = layer.dxf.name
        layers_info[name] = {
            "color": layer.dxf.color if hasattr(layer.dxf, "color") else None,
            "linetype": layer.dxf.linetype if hasattr(layer.dxf, "linetype") else None,
            "category": classify_layer(name),
            "entity_count": 0,
            "entity_types": {},
        }

    # Compte entités par layer + type
    for entity in msp:
        layer_name = entity.dxf.layer
        if layer_name not in layers_info:
            # Layer utilisé mais pas dans la table des layers (rare)
            layers_info[layer_name] = {
                "color": None,
                "linetype": None,
                "category": classify_layer(layer_name),
                "entity_count": 0,
                "entity_types": {},
            }
        info = layers_info[layer_name]
        info["entity_count"] += 1
        etype = entity.dxftype()
        info["entity_types"][etype] = info["entity_types"].get(etype, 0) + 1

    # Agrégations par catégorie sémantique
    by_category: dict[str, dict] = {}
    for name, info in layers_info.items():
        cat = info["category"]
        if cat not in by_category:
            by_category[cat] = {"layers": [], "total_entities": 0}
        by_category[cat]["layers"].append(name)
        by_category[cat]["total_entities"] += info["entity_count"]

    # Bounding box approximative
    try:
        bbox = msp.bbox()
        extents = {
            "min_x": bbox.extmin.x, "min_y": bbox.extmin.y,
            "max_x": bbox.extmax.x, "max_y": bbox.extmax.y,
        }
    except Exception:
        extents = None

    return {
        "file": dxf_path.name,
        "dxf_version": doc.dxfversion,
        "n_layers": len(layers_info),
        "n_entities": sum(i["entity_count"] for i in layers_info.values()),
        "extents": extents,
        "layers": layers_info,
        "by_category": by_category,
    }


def render_dxf_to_png(dxf_path: Path, out_png: Path, dpi: int = 200) -> bool:
    """Rend un DXF en PNG via le backend Matplotlib de ezdxf."""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        fig, ax = plt.subplots(figsize=(10, 10))
        ctx = RenderContext(doc)
        backend = MatplotlibBackend(ax)
        Frontend(ctx, backend).draw_layout(msp, finalize=True)

        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_png), dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return True
    except Exception as e:
        print(f"  ! Render failed: {e}")
        return False


def _entity_segments(entity) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Extrait les segments d'une entité DXF sous forme [(p1, p2), ...].

    Couvre les types les plus communs (LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE).
    Les types non gérés (HATCH, INSERT, SPLINE, etc.) retournent [].
    """
    import math
    etype = entity.dxftype()
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    try:
        if etype == "LINE":
            p1 = entity.dxf.start
            p2 = entity.dxf.end
            segs.append(((p1.x, p1.y), (p2.x, p2.y)))
        elif etype == "LWPOLYLINE":
            pts = list(entity.get_points("xy"))
            for i in range(len(pts) - 1):
                segs.append(((pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1])))
            if entity.is_closed and len(pts) >= 2:
                segs.append(((pts[-1][0], pts[-1][1]), (pts[0][0], pts[0][1])))
        elif etype == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            for i in range(len(pts) - 1):
                segs.append((pts[i], pts[i + 1]))
            if entity.is_closed and len(pts) >= 2:
                segs.append((pts[-1], pts[0]))
        elif etype == "ARC":
            # Discrétise l'arc en 16 segments
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            a0 = math.radians(entity.dxf.start_angle)
            a1 = math.radians(entity.dxf.end_angle)
            if a1 < a0:
                a1 += 2 * math.pi
            n = 16
            for i in range(n):
                t0 = a0 + (a1 - a0) * i / n
                t1 = a0 + (a1 - a0) * (i + 1) / n
                segs.append((
                    (cx + r * math.cos(t0), cy + r * math.sin(t0)),
                    (cx + r * math.cos(t1), cy + r * math.sin(t1)),
                ))
        elif etype == "CIRCLE":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            n = 24
            for i in range(n):
                t0 = 2 * math.pi * i / n
                t1 = 2 * math.pi * (i + 1) / n
                segs.append((
                    (cx + r * math.cos(t0), cy + r * math.sin(t0)),
                    (cx + r * math.cos(t1), cy + r * math.sin(t1)),
                ))
    except Exception:
        pass
    return segs


def render_overlay(
    dxf_path: Path, out_png: Path, highlight_categories: list[str], color: str,
) -> bool:
    """Rend un DXF en PNG avec UNIQUEMENT les entités d'une catégorie surlignées.

    Pipeline raw matplotlib (pas le backend ezdxf qui plante sur certaines
    géométries). On itère toutes les entités, on extrait leurs segments, on
    dessine en gris clair pour le contexte et en couleur vive pour la cible.
    """
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        target_layers = {
            layer.dxf.name for layer in doc.layers
            if classify_layer(layer.dxf.name) in highlight_categories
        }
        if not target_layers:
            print(f"  ! Aucun layer de catégorie {highlight_categories}")
            return False

        # Collecte les segments par groupe (contexte / cible)
        context_segs: list = []
        target_segs: list = []
        for entity in msp:
            segs = _entity_segments(entity)
            if not segs:
                continue
            if entity.dxf.layer in target_layers:
                target_segs.extend(segs)
            else:
                context_segs.extend(segs)

        if not target_segs:
            print(f"  ! Aucun segment dans les layers cibles {target_layers}")
            return False

        fig, ax = plt.subplots(figsize=(12, 12))
        ax.set_aspect("equal")
        ax.axis("off")

        if context_segs:
            ctx_lc = LineCollection(
                context_segs, colors="lightgray", linewidths=0.4, antialiased=True,
            )
            ax.add_collection(ctx_lc)

        tgt_lc = LineCollection(
            target_segs, colors=color, linewidths=1.5, antialiased=True,
        )
        ax.add_collection(tgt_lc)

        # Calcule l'extent depuis TOUS les segments
        all_xs, all_ys = [], []
        for (p1, p2) in (context_segs + target_segs):
            all_xs.extend([p1[0], p2[0]])
            all_ys.extend([p1[1], p2[1]])
        if all_xs and all_ys:
            mx, Mx = min(all_xs), max(all_xs)
            my, My = min(all_ys), max(all_ys)
            pad = max((Mx - mx), (My - my)) * 0.02
            ax.set_xlim(mx - pad, Mx + pad)
            ax.set_ylim(my - pad, My + pad)

        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_png), dpi=180, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return True
    except Exception as e:
        print(f"  ! Overlay render failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def process_plan(
    src_path: Path, dxf_intermediate_dir: Path, output_dir: Path,
    skip_raster: bool = False, step_timeout: int = 45,
) -> dict:
    """Process un seul plan (DWG ou DXF) — convert si nécessaire, parse, render.

    `skip_raster` : skip le rendu raster lourd via Frontend matplotlib
        (sur gros DWG ça hang, on garde juste l'overlay LineCollection rapide)
    `step_timeout` : timeout en secondes par étape (rendu/overlay)
    """
    sys.stdout.write(f"[{src_path.name}] ... ")
    sys.stdout.flush()

    result = {"file": src_path.name, "status": "pending"}

    # 1. Get DXF
    if src_path.suffix.lower() == ".dwg":
        dxf_path = convert_dwg_to_dxf(src_path, dxf_intermediate_dir)
        if dxf_path is None:
            print("CONV FAILED")
            result["status"] = "conversion_failed"
            return result
    elif src_path.suffix.lower() == ".dxf":
        dxf_path = src_path
    else:
        print("UNSUPPORTED")
        result["status"] = "unsupported_format"
        return result

    # 2. Parse
    try:
        report = parse_dxf(dxf_path)
    except Exception as e:
        print(f"PARSE FAILED: {e}")
        result["status"] = "parse_failed"
        result["error"] = str(e)
        return result

    n_walls = report["by_category"].get("wall", {}).get("total_entities", 0)
    n_doors = report["by_category"].get("door", {}).get("total_entities", 0)
    n_unknown = report["by_category"].get("unknown", {}).get("total_entities", 0)

    # 3. Rendu PNG
    plan_out = output_dir / src_path.stem
    plan_out.mkdir(parents=True, exist_ok=True)

    render_status = []

    if not skip_raster:
        raster_png = plan_out / "raster.png"
        try:
            with with_timeout(step_timeout):
                if render_dxf_to_png(dxf_path, raster_png):
                    render_status.append("R")
        except StepTimeout:
            render_status.append("R-TIMEOUT")

    if n_walls > 0:
        walls_png = plan_out / "overlay_walls.png"
        try:
            with with_timeout(step_timeout):
                if render_overlay(dxf_path, walls_png, ["wall"], "red"):
                    render_status.append("W")
        except StepTimeout:
            render_status.append("W-TIMEOUT")

    if n_doors > 0:
        doors_png = plan_out / "overlay_doors.png"
        try:
            with with_timeout(step_timeout):
                if render_overlay(dxf_path, doors_png, ["door"], "green"):
                    render_status.append("D")
        except StepTimeout:
            render_status.append("D-TIMEOUT")

    # 4. Sauvegarde le rapport JSON
    report_path = plan_out / "report.json"
    with report_path.open("w") as f:
        json.dump(report, f, indent=2, default=str)

    print(
        f"OK  layers={report['n_layers']:3d}  ent={report['n_entities']:6d}  "
        f"walls={n_walls:4d}  doors={n_doors:3d}  unk={n_unknown:6d}  "
        f"render={'/'.join(render_status) or '-'}"
    )
    result["status"] = "ok"
    result["report"] = report
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans-dir", default=str(DEFAULT_DWG_DIR))
    parser.add_argument("--dxf-dir", default=str(DEFAULT_DXF_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--skip-raster", action="store_true",
        help="Skip le rendu raster Frontend matplotlib (lent sur gros DWG)",
    )
    parser.add_argument(
        "--step-timeout", type=int, default=45,
        help="Timeout en sec par étape de rendu (default 45)",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip les plans déjà traités (report.json existe)",
    )
    args = parser.parse_args()

    plans_dir = Path(args.plans_dir)
    dxf_dir = Path(args.dxf_dir)
    out_dir = Path(args.out_dir)

    if not plans_dir.exists():
        print(f"ERROR: {plans_dir} n'existe pas")
        sys.exit(1)

    files = sorted(
        [p for p in plans_dir.iterdir() if p.suffix.lower() in (".dwg", ".dxf")]
    )
    if not files:
        print(f"Aucun fichier .dwg ou .dxf dans {plans_dir}")
        print(f"Dépose tes fichiers et relance le script.")
        sys.exit(0)

    print(f"=== DWG/DXF pipeline ===")
    print(f"Input  : {plans_dir} ({len(files)} fichiers)")
    print(f"DXF    : {dxf_dir} (intermédiaire si conversion)")
    print(f"Output : {out_dir}")
    print(f"ODA File Converter : {'✓ installé' if has_oda() else '✗ ABSENT (DWG seront skippés)'}")

    results = []
    for i, f in enumerate(files, 1):
        if args.skip_existing:
            existing_report = out_dir / f.stem / "report.json"
            if existing_report.exists():
                print(f"[{i:3d}/{len(files)}] [{f.name}] SKIP (already done)")
                continue
        print(f"[{i:3d}/{len(files)}] ", end="")
        r = process_plan(
            f, dxf_dir, out_dir,
            skip_raster=args.skip_raster,
            step_timeout=args.step_timeout,
        )
        results.append(r)

    # Synthèse
    print(f"\n=== Synthèse ===")
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"Plans traités OK : {ok} / {len(files)}")
    for r in results:
        if r["status"] != "ok":
            print(f"  ! {r['file']} : {r['status']}")

    # Inventaire global des catégories de layers détectées
    cat_totals: dict[str, int] = {}
    for r in results:
        if r["status"] != "ok":
            continue
        for cat, info in r["report"]["by_category"].items():
            cat_totals[cat] = cat_totals.get(cat, 0) + info["total_entities"]
    if cat_totals:
        print(f"\n=== Inventaire global (toutes catégories confondues) ===")
        for cat, n in sorted(cat_totals.items(), key=lambda x: -x[1]):
            print(f"  {cat:12s} : {n:6d} entités")


if __name__ == "__main__":
    main()
