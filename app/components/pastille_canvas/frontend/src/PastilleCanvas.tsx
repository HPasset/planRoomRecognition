import { useEffect, useRef, useState, useCallback, useMemo, memo } from "react";
import {
  Streamlit,
  withStreamlitConnection,
  ComponentProps,
} from "streamlit-component-lib";

export interface Pastille {
  id: string;
  type: string;
  label: string;
  x: number;            // px image originale
  y: number;            // px image originale
  color: string;
}

export interface PaletteType {
  type: string;
  label: string;
  color: string;
}

/**
 * Polygone de segmentation à dessiner en overlay sous les pastilles.
 * `points` est en coord image originale (px).
 */
export interface SegPolygon {
  type_name: string;     // ex: "Kitchen"
  points: [number, number][];
  fill: string;          // ex: "rgba(255,200,100,0.35)"
  stroke: string;        // ex: "rgb(255,200,100)"
}

/**
 * Bbox YOLO Brique A (meubles). Coords image originale (px). Non interactif.
 */
export interface YoloBox {
  class_name: string;    // ex: "Bed", "Toilet"
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;    // 0-1
  color: string;         // ex: "rgb(160,82,45)"
}

/**
 * Instance unique d'équipement électrique sur le plan (1 prise = 1 instance,
 * même si la ligne devis a Qté=6). Coords image originale (px).
 */
export interface EquipmentInstance {
  id: string;
  type: string;
  room: string;
  x: number;
  y: number;
  color: string;
}

/**
 * Chip palette équipement (5 entrées, une par type) pour drag-in.
 */
export interface EquipmentPaletteType {
  type: string;
  label: string;
  color: string;
  svg_id: string;
}

interface Args {
  image_data: string;
  image_width: number;
  image_height: number;
  initial_pastilles: Pastille[];
  palette: PaletteType[];
  seg_polygons?: SegPolygon[];
  yolo_boxes?: YoloBox[];
  equipments?: EquipmentInstance[];
  equip_palette?: EquipmentPaletteType[];
}

interface DropResult {
  /** delta en image px (positif = droite/bas) */
  dxImg: number;
  dyImg: number;
  /** Position finale du pointer en client px */
  finalClientX: number;
  finalClientY: number;
  /** Position finale en image px */
  finalImgX: number;
  finalImgY: number;
  /** True si la position finale est dans la bbox image */
  insideImage: boolean;
}

// ============================================================================
// PastilleChip : drag via pointer events natifs + DOM imperative
// → listeners attachés UNE fois (deps []) → pas de race condition au remount
// → drag = style.transform direct, ZÉRO re-render React pendant le drag
// → autres pastilles strictement immobiles
// ============================================================================

interface PastilleChipProps {
  pastille: Pastille;
  imageWidth: number;
  imageHeight: number;
  imgRef: React.RefObject<HTMLImageElement>;
  onDrop: (id: string, drop: DropResult) => void;
}

const PastilleChip = memo(function PastilleChip({
  pastille, imageWidth, imageHeight, imgRef, onDrop,
}: PastilleChipProps) {
  const elRef = useRef<HTMLDivElement>(null);

  // Refs miroir → accès aux valeurs courantes depuis listeners stables
  const pastilleRef = useRef(pastille);
  pastilleRef.current = pastille;
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const imgRefRef = useRef(imgRef);
  imgRefRef.current = imgRef;
  // Refs pour les dimensions (utilisées dans listener stable)
  const imageWidthRef = useRef(imageWidth);
  imageWidthRef.current = imageWidth;
  const imageHeightRef = useRef(imageHeight);
  imageHeightRef.current = imageHeight;

  // Setup listeners UNE fois par chip
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    let isDragging = false;
    let startClientX = 0;
    let startClientY = 0;
    let lastDx = 0;
    let lastDy = 0;

    const onPointerDown = (e: PointerEvent) => {
      // Évite la propagation et le drag natif HTML5
      e.preventDefault();
      e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      isDragging = true;
      startClientX = e.clientX;
      startClientY = e.clientY;
      lastDx = 0;
      lastDy = 0;
      el.style.zIndex = "10";
      el.style.opacity = "0.85";
      el.style.cursor = "grabbing";
      el.style.boxShadow = "0 6px 14px rgba(0, 0, 0, 0.35)";
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging) return;
      lastDx = e.clientX - startClientX;
      lastDy = e.clientY - startClientY;
      el.style.transform =
        `translate3d(${lastDx}px, ${lastDy}px, 0) translate(-50%, -50%)`;
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch { /* déjà release */ }

      // Calcule la position finale en image px
      const img = imgRefRef.current.current;
      const imgW = imageWidthRef.current;
      const imgH = imageHeightRef.current;
      if (!img) {
        // Reset visuel
        el.style.zIndex = "1";
        el.style.opacity = "1";
        el.style.cursor = "grab";
        el.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.15)";
        el.style.transform = "translate(-50%, -50%)";
        return;
      }
      const rect = img.getBoundingClientRect();
      const scaleX = rect.width / imgW;
      const scaleY = rect.height / imgH;
      const dxImg = lastDx / scaleX;
      const dyImg = lastDy / scaleY;
      const finalImgX = Math.round(pastilleRef.current.x + dxImg);
      const finalImgY = Math.round(pastilleRef.current.y + dyImg);
      const insideImage =
        finalImgX >= 0 && finalImgX <= imgW
        && finalImgY >= 0 && finalImgY <= imgH;

      // CRITIQUE : avant de retirer le translate3d du drag, on POSE la
      // nouvelle position via left/top imperative. Comme ça quand React
      // re-render (avec les mêmes valeurs), le visuel ne saute pas.
      if (insideImage) {
        const newLeftPct = (finalImgX / imgW) * 100;
        const newTopPct = (finalImgY / imgH) * 100;
        el.style.left = `${newLeftPct}%`;
        el.style.top = `${newTopPct}%`;
      }
      el.style.transform = "translate(-50%, -50%)";
      el.style.zIndex = "1";
      el.style.opacity = "1";
      el.style.cursor = "grab";
      el.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.15)";

      onDropRef.current(pastilleRef.current.id, {
        dxImg, dyImg,
        finalClientX: e.clientX,
        finalClientY: e.clientY,
        finalImgX, finalImgY,
        insideImage,
      });
    };

    const onPointerCancel = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch { /* déjà release */ }
      el.style.zIndex = "1";
      el.style.opacity = "1";
      el.style.cursor = "grab";
      el.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.15)";
      el.style.transform = "translate(-50%, -50%)";
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerCancel);

    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerCancel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // ZÉRO deps : listeners attachés UNE fois par chip lifetime

  const leftPercent = (pastille.x / imageWidth) * 100;
  const topPercent = (pastille.y / imageHeight) * 100;

  return (
    <div
      ref={elRef}
      className="pc-pastille"
      style={{
        position: "absolute",
        left: `${leftPercent}%`,
        top: `${topPercent}%`,
        transform: "translate(-50%, -50%)",
        backgroundColor: pastille.color,
        cursor: "grab",
        touchAction: "none",
        zIndex: 1,
        boxShadow: "0 2px 4px rgba(0, 0, 0, 0.15)",
        willChange: "transform",
      }}
      title={pastille.label}
    >
      {pastille.label}
    </div>
  );
});

// ============================================================================
// PaletteChip : drag via pointer events natifs, ghost en position fixed
// ============================================================================

interface PaletteChipProps {
  pt: PaletteType;
  onDropOnCanvas: (pt: PaletteType, clientX: number, clientY: number) => void;
}

const PaletteChip = memo(function PaletteChip({ pt, onDropOnCanvas }: PaletteChipProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const ptRef = useRef(pt);
  ptRef.current = pt;
  const onDropRef = useRef(onDropOnCanvas);
  onDropRef.current = onDropOnCanvas;

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    let isDragging = false;
    let ghost: HTMLDivElement | null = null;

    const createGhost = (clientX: number, clientY: number) => {
      const g = document.createElement("div");
      g.textContent = ptRef.current.label;
      g.style.cssText = `
        position: fixed;
        left: ${clientX}px;
        top: ${clientY}px;
        transform: translate(-50%, -50%);
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        color: #1a1a1a;
        background-color: ${ptRef.current.color};
        border: 2px dashed rgba(0, 0, 0, 0.5);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
        opacity: 0.7;
        z-index: 9999;
        pointer-events: none;
        white-space: nowrap;
      `;
      document.body.appendChild(g);
      return g;
    };

    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      isDragging = true;
      ghost = createGhost(e.clientX, e.clientY);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || !ghost) return;
      ghost.style.left = `${e.clientX}px`;
      ghost.style.top = `${e.clientY}px`;
    };

    const cleanup = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch { /* déjà release */ }
      if (ghost) {
        ghost.remove();
        ghost = null;
      }
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      const finalX = e.clientX;
      const finalY = e.clientY;
      cleanup(e);
      onDropRef.current(ptRef.current, finalX, finalY);
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", cleanup);

    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", cleanup);
      if (ghost) ghost.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={elRef}
      className="pc-palette-chip"
      style={{
        backgroundColor: pt.color,
        touchAction: "none",
        cursor: "grab",
      }}
      title={`Drag sur le plan pour ajouter une ${pt.label}`}
    >
      {pt.label}
    </div>
  );
});

/**
 * Rend l'icône SVG d'un équipement par son svg_id. Style NF EN 60617 stylisé.
 */
interface SvgEquipIconProps {
  svgId: string;
  color: string;
  size?: number;
}

function SvgEquipIcon({ svgId, color, size = 22 }: SvgEquipIconProps) {
  const sw = 2.5;
  switch (svgId) {
    case "socket":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="13" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="20" y1="7" x2="20" y2="20" stroke={color} strokeWidth={sw}/>
        </svg>
      );
    case "switch":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="10" cy="20" r="3" fill={color}/>
          <circle cx="30" cy="20" r="3" fill={color}/>
          <line x1="10" y1="20" x2="28" y2="10" stroke={color} strokeWidth={sw}/>
        </svg>
      );
    case "light":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="12" fill="#fff9c4" stroke={color} strokeWidth={sw}/>
          <line x1="13" y1="13" x2="27" y2="27" stroke={color} strokeWidth={2}/>
          <line x1="27" y1="13" x2="13" y2="27" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "specfeed":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="14" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="20" y1="4" x2="20" y2="20" stroke={color} strokeWidth={sw}/>
          <line x1="14" y1="2" x2="20" y2="6" stroke={color} strokeWidth={2}/>
          <line x1="26" y1="2" x2="20" y2="6" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "rj45":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="10" y="14" width="20" height="12" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="14" y1="14" x2="14" y2="9" stroke={color} strokeWidth={2}/>
          <line x1="20" y1="14" x2="20" y2="9" stroke={color} strokeWidth={2}/>
          <line x1="26" y1="14" x2="26" y2="9" stroke={color} strokeWidth={2}/>
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="14" fill="white" stroke={color} strokeWidth={sw}/>
          <text x="20" y="25" textAnchor="middle" fontSize="14" fill={color}>?</text>
        </svg>
      );
  }
}

/**
 * Résultat d'un drop d'équipement (passé au handler Python via onEquipDrop).
 */
interface EquipDropResult {
  finalImgX: number;
  finalImgY: number;
  insideImage: boolean;
}

/**
 * Chip équipement positionné sur le plan (en % image, comme les pastilles).
 * Drag activé en Phase 3 — pattern pointer events natifs (idem PastilleChip).
 */
interface EquipmentChipProps {
  equipment: EquipmentInstance;
  svgId: string;
  imageWidth: number;
  imageHeight: number;
  imgRef: React.RefObject<HTMLImageElement>;
  onDrop: (id: string, drop: EquipDropResult) => void;
}

const EquipmentChip = memo(function EquipmentChip({
  equipment, svgId, imageWidth, imageHeight, imgRef, onDrop,
}: EquipmentChipProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const equipmentRef = useRef(equipment);
  equipmentRef.current = equipment;
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const imgRefRef = useRef(imgRef);
  imgRefRef.current = imgRef;
  const imageWidthRef = useRef(imageWidth);
  imageWidthRef.current = imageWidth;
  const imageHeightRef = useRef(imageHeight);
  imageHeightRef.current = imageHeight;

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let isDragging = false;
    let startClientX = 0, startClientY = 0;
    let lastDx = 0, lastDy = 0;

    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      isDragging = true;
      startClientX = e.clientX;
      startClientY = e.clientY;
      lastDx = 0; lastDy = 0;
      el.style.zIndex = "20";
      el.style.opacity = "0.85";
      el.style.cursor = "grabbing";
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging) return;
      lastDx = e.clientX - startClientX;
      lastDy = e.clientY - startClientY;
      el.style.transform =
        `translate3d(${lastDx}px, ${lastDy}px, 0) translate(-50%, -50%)`;
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
      const img = imgRefRef.current.current;
      const imgW = imageWidthRef.current;
      const imgH = imageHeightRef.current;
      if (!img) {
        el.style.zIndex = "2"; el.style.opacity = "1";
        el.style.cursor = "grab"; el.style.transform = "translate(-50%, -50%)";
        return;
      }
      const rect = img.getBoundingClientRect();
      const scaleX = rect.width / imgW;
      const scaleY = rect.height / imgH;
      const dxImg = lastDx / scaleX;
      const dyImg = lastDy / scaleY;
      const finalImgX = Math.round(equipmentRef.current.x + dxImg);
      const finalImgY = Math.round(equipmentRef.current.y + dyImg);
      const insideImage =
        finalImgX >= 0 && finalImgX <= imgW
        && finalImgY >= 0 && finalImgY <= imgH;
      if (insideImage) {
        const newLeftPct = (finalImgX / imgW) * 100;
        const newTopPct = (finalImgY / imgH) * 100;
        el.style.left = `${newLeftPct}%`;
        el.style.top = `${newTopPct}%`;
      }
      el.style.transform = "translate(-50%, -50%)";
      el.style.zIndex = "2";
      el.style.opacity = "1";
      el.style.cursor = "grab";
      onDropRef.current(equipmentRef.current.id, {
        finalImgX, finalImgY, insideImage,
      });
    };
    const onPointerCancel = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
      el.style.zIndex = "2"; el.style.opacity = "1";
      el.style.cursor = "grab"; el.style.transform = "translate(-50%, -50%)";
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerCancel);
    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerCancel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const leftPercent = (equipment.x / imageWidth) * 100;
  const topPercent = (equipment.y / imageHeight) * 100;
  return (
    <div
      ref={elRef}
      style={{
        position: "absolute",
        left: `${leftPercent}%`,
        top: `${topPercent}%`,
        transform: "translate(-50%, -50%)",
        zIndex: 2,
        touchAction: "none",
        cursor: "grab",
        padding: 5,
        background: "rgba(255,255,255,0.6)",
        borderRadius: "50%",
        boxShadow: "0 1px 2px rgba(0,0,0,0.15)",
      }}
      title={`${equipment.type} (${equipment.room})`}
    >
      <SvgEquipIcon svgId={svgId} color={equipment.color} size={22} />
    </div>
  );
});

/**
 * Chip palette équipement (statique pour Phase 2, drag-in en Phase 4).
 */
interface EquipmentPaletteChipProps {
  pt: EquipmentPaletteType;
}

const EquipmentPaletteChip = memo(function EquipmentPaletteChip({
  pt,
}: EquipmentPaletteChipProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        border: `2px solid ${pt.color}`,
        borderRadius: 18,
        background: "white",
        cursor: "grab",
        touchAction: "none",
        fontSize: 11,
        fontWeight: 600,
        color: "#333",
        whiteSpace: "nowrap",
      }}
      title={`Drag sur le plan pour ajouter un(e) ${pt.label}`}
    >
      <SvgEquipIcon svgId={pt.svg_id} color={pt.color} size={18} />
      {pt.label}
    </div>
  );
});

// ============================================================================
// Composant principal
// ============================================================================

function PastilleCanvas({ args }: ComponentProps) {
  const typedArgs = args as Args;
  const {
    image_data,
    image_width,
    image_height,
    initial_pastilles,
    palette,
    seg_polygons,
    yolo_boxes,
    equipments,
    equip_palette,
  } = typedArgs;

  const [pastilles, setPastilles] = useState<Pastille[]>(initial_pastilles ?? []);
  const [equipmentsState, setEquipmentsState] = useState<EquipmentInstance[]>(
    equipments ?? []
  );

  const imgRef = useRef<HTMLImageElement>(null);
  const lastSentJsonRef = useRef<string>("");

  const equipSvgMap = useMemo(
    () => Object.fromEntries((equip_palette ?? []).map((pt) => [pt.type, pt.svg_id])),
    [equip_palette]
  );

  // setFrameHeight : seulement quand contenu change vraiment
  useEffect(() => {
    Streamlit.setFrameHeight();
  }, [pastilles.length, equipmentsState.length, palette.length, image_data]);

  // Notify Python à chaque changement réel de pastilles ou équipements
  useEffect(() => {
    const payload = { pastilles, equipments: equipmentsState };
    const json = JSON.stringify(payload);
    if (json === lastSentJsonRef.current) return;
    lastSentJsonRef.current = json;
    Streamlit.setComponentValue(payload);
  }, [pastilles, equipmentsState]);

  // Re-sync depuis Python : SEULEMENT add/remove, jamais les positions.
  // React owns les positions des pastilles. Si Python overwrite, il ré-injecte
  // l'OLD position (parce que session_state est mis à jour APRÈS le call
  // pastille_canvas() côté Python, donc Python a un cycle de retard sur les
  // positions). On ne sync que :
  //   - SUPPRESSION : id présent dans React state mais absent de initial_pastilles
  //     → typiquement quand l'user supprime une row via 🗑️ table éditeur
  //   - AJOUT : id présent dans initial_pastilles mais absent de React state
  //     → cas rare (Python ajoute une pastille sans passer par React)
  // Les pastilles existantes (même id dans les 2) gardent LA position React.
  useEffect(() => {
    const incoming = initial_pastilles ?? [];
    const incomingIds = new Set(incoming.map((p) => p.id));
    setPastilles((prev) => {
      const currentIds = new Set(prev.map((p) => p.id));
      // Skip si exactement les mêmes IDs (cas le plus fréquent : Python renvoie
      // juste ce que React a envoyé) → évite re-render inutile
      if (
        incomingIds.size === currentIds.size
        && [...incomingIds].every((id) => currentIds.has(id))
      ) {
        return prev;
      }
      // Supprime les pastilles qui ne sont plus dans initial_pastilles
      const filtered = prev.filter((p) => incomingIds.has(p.id));
      // Ajoute les nouvelles pastilles (présentes dans incoming, absentes du state)
      const added = incoming.filter((p) => !currentIds.has(p.id));
      return [...filtered, ...added];
    });
  }, [initial_pastilles]);

  // Handler drop pastille existante (commit position ou suppression)
  const handlePastilleDrop = useCallback(
    (id: string, drop: DropResult) => {
      if (!drop.insideImage) {
        setPastilles((prev) => prev.filter((p) => p.id !== id));
      } else {
        setPastilles((prev) =>
          prev.map((p) =>
            p.id === id ? { ...p, x: drop.finalImgX, y: drop.finalImgY } : p,
          ),
        );
      }
    },
    [],
  );

  // Re-sync équipements depuis Python : SEULEMENT add/remove, jamais les
  // positions (React owns positions, idem pastilles). Voir commentaire détaillé
  // sur le sync pastilles ci-dessus.
  useEffect(() => {
    const incoming = equipments ?? [];
    const incomingIds = new Set(incoming.map((e) => e.id));
    setEquipmentsState((prev) => {
      const currentIds = new Set(prev.map((e) => e.id));
      if (incomingIds.size === currentIds.size
          && [...incomingIds].every((id) => currentIds.has(id))) {
        return prev;
      }
      const filtered = prev.filter((e) => incomingIds.has(e.id));
      const added = incoming.filter((e) => !currentIds.has(e.id));
      return [...filtered, ...added];
    });
  }, [equipments]);

  // Handler drop équipement existant (commit position ou suppression hors plan)
  const handleEquipmentDrop = useCallback(
    (id: string, drop: EquipDropResult) => {
      if (!drop.insideImage) {
        setEquipmentsState((prev) => prev.filter((e) => e.id !== id));
      } else {
        setEquipmentsState((prev) =>
          prev.map((e) =>
            e.id === id ? { ...e, x: drop.finalImgX, y: drop.finalImgY } : e,
          ),
        );
      }
    },
    [],
  );

  // Handler drop depuis palette (ajout nouvelle pastille)
  const handlePaletteDrop = useCallback(
    (pt: PaletteType, clientX: number, clientY: number) => {
      const img = imgRef.current;
      if (!img) return;
      const rect = img.getBoundingClientRect();
      const insideX = clientX >= rect.left && clientX <= rect.right;
      const insideY = clientY >= rect.top && clientY <= rect.bottom;
      if (!insideX || !insideY) return;
      const scaleX = rect.width / image_width;
      const scaleY = rect.height / image_height;
      const x = Math.round((clientX - rect.left) / scaleX);
      const y = Math.round((clientY - rect.top) / scaleY);
      const newId = `new_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      setPastilles((prev) => [
        ...prev,
        {
          id: newId,
          type: pt.type,
          label: pt.label,
          x, y,
          color: pt.color,
        },
      ]);
    },
    [image_width, image_height],
  );

  return (
    <div className="pc-root">
      <div className="pc-canvas-wrapper">
        <img
          ref={imgRef}
          src={image_data}
          alt="Plan"
          className="pc-canvas-image"
          onLoad={() => Streamlit.setFrameHeight()}
          draggable={false}
        />
        {/* SVG overlay segmentation (entre image et pastilles, non interactif) */}
        {seg_polygons && seg_polygons.length > 0 && (
          <svg
            className="pc-seg-overlay"
            viewBox={`0 0 ${image_width} ${image_height}`}
            preserveAspectRatio="none"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              pointerEvents: "none",
              zIndex: 0,
            }}
          >
            {seg_polygons.map((sp, idx) => (
              <polygon
                key={`seg_${idx}`}
                points={sp.points.map((pt) => `${pt[0]},${pt[1]}`).join(" ")}
                fill={sp.fill}
                stroke={sp.stroke}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
        )}
        {/* SVG overlay YOLO meubles (au-dessus segmentation, sous pastilles).
            Rectangles + labels. Non interactif (pointer-events: none). */}
        {yolo_boxes && yolo_boxes.length > 0 && (
          <svg
            className="pc-yolo-overlay"
            viewBox={`0 0 ${image_width} ${image_height}`}
            preserveAspectRatio="none"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              pointerEvents: "none",
              zIndex: 0,
            }}
          >
            {yolo_boxes.map((b, idx) => {
              const w = b.x2 - b.x1;
              const h = b.y2 - b.y1;
              const label = `${b.class_name} ${b.confidence.toFixed(2)}`;
              // Hauteur du fond du label proportionnelle à la taille image
              // (les coords sont en image px, le SVG scale auto)
              const labelH = Math.max(14, image_height * 0.018);
              const labelFontSize = Math.max(10, image_height * 0.013);
              return (
                <g key={`yolo_${idx}`}>
                  <rect
                    x={b.x1}
                    y={b.y1}
                    width={w}
                    height={h}
                    fill="none"
                    stroke={b.color}
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                  {/* Fond du label pour lisibilité */}
                  <rect
                    x={b.x1}
                    y={b.y1 - labelH}
                    width={Math.min(w, label.length * labelFontSize * 0.6)}
                    height={labelH}
                    fill={b.color}
                    opacity={0.85}
                  />
                  <text
                    x={b.x1 + 3}
                    y={b.y1 - labelH * 0.25}
                    fontSize={labelFontSize}
                    fill="white"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {label}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
        {pastilles.map((p) => (
          <PastilleChip
            key={p.id}
            pastille={p}
            imageWidth={image_width}
            imageHeight={image_height}
            imgRef={imgRef}
            onDrop={handlePastilleDrop}
          />
        ))}
        {/* Équipements électriques (drag actif Phase 3) */}
        {equipmentsState.length > 0 && equipmentsState.map((eq) => (
          <EquipmentChip
            key={eq.id}
            equipment={eq}
            svgId={equipSvgMap[eq.type] ?? eq.type}
            imageWidth={image_width}
            imageHeight={image_height}
            imgRef={imgRef}
            onDrop={handleEquipmentDrop}
          />
        ))}
      </div>

      {/* Palette équipements (sous le canvas, drag-in Phase 4) */}
      {equip_palette && equip_palette.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            padding: "8px 4px",
            marginTop: 6,
            borderTop: "1px dashed #d0d7e2",
          }}
        >
          <div style={{ fontSize: 11, color: "#666", marginRight: 8, paddingTop: 8 }}>
            🔌 Drag depuis cette palette pour ajouter un équipement :
          </div>
          {equip_palette.map((pt) => (
            <EquipmentPaletteChip key={pt.type} pt={pt} />
          ))}
        </div>
      )}

      <div className="pc-palette">
        <div className="pc-palette-title">Palette</div>
        {palette.map((pt) => (
          <PaletteChip
            key={pt.type}
            pt={pt}
            onDropOnCanvas={handlePaletteDrop}
          />
        ))}
        <div className="pc-palette-hint">
          Drag depuis la palette → ajout sur le plan.<br />
          Drag les pastilles → déplacement.<br />
          Sors du plan → suppression.
        </div>
      </div>
    </div>
  );
}

export default withStreamlitConnection(PastilleCanvas);
