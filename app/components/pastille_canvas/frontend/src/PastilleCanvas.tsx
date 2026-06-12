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
  rotation?: number;    // deg ; 0 = horizontal (défaut), -90 = vertical
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
  uncertain?: boolean;
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
  equip_visible_types?: string[];
  pastille_to_devis_room?: Record<string, string>;
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
      const rot = pastilleRef.current.rotation ?? 0;
      el.style.transform =
        `translate3d(${lastDx}px, ${lastDy}px, 0) translate(-50%, -50%) rotate(${rot}deg)`;
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch { /* déjà release */ }

      // Calcule la position finale en image px
      const img = imgRefRef.current.current;
      const imgW = imageWidthRef.current;
      const imgH = imageHeightRef.current;
      const _rotRest = pastilleRef.current.rotation ?? 0;
      if (!img) {
        // Reset visuel
        el.style.zIndex = "1";
        el.style.opacity = "1";
        el.style.cursor = "grab";
        el.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.15)";
        el.style.transform = `translate(-50%, -50%) rotate(${_rotRest}deg)`;
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
      el.style.transform = `translate(-50%, -50%) rotate(${_rotRest}deg)`;
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
      const _rotCancel = pastilleRef.current.rotation ?? 0;
      el.style.zIndex = "1";
      el.style.opacity = "1";
      el.style.cursor = "grab";
      el.style.boxShadow = "0 2px 4px rgba(0, 0, 0, 0.15)";
      el.style.transform = `translate(-50%, -50%) rotate(${_rotCancel}deg)`;
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
  const rotation = pastille.rotation ?? 0;

  return (
    <div
      ref={elRef}
      className="pc-pastille"
      style={{
        position: "absolute",
        left: `${leftPercent}%`,
        top: `${topPercent}%`,
        transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
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
    case "oven":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <rect x="10" y="12" width="20" height="12" rx="1" fill="none" stroke={color} strokeWidth={2}/>
          <text x="20" y="25" textAnchor="middle" fontSize="10" fontWeight="bold" fill={color}>F</text>
        </svg>
      );
    case "cooktop":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <circle cx="15" cy="17" r="4" fill="none" stroke={color} strokeWidth={2}/>
          <circle cx="25" cy="17" r="4" fill="none" stroke={color} strokeWidth={2}/>
          <circle cx="15" cy="27" r="4" fill="none" stroke={color} strokeWidth={2}/>
          <circle cx="25" cy="27" r="4" fill="none" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "dishwasher":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <text x="20" y="25" textAnchor="middle" fontSize="10" fontWeight="bold" fill={color}>LV</text>
        </svg>
      );
    case "washingmachine":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <circle cx="20" cy="22" r="8" fill="none" stroke={color} strokeWidth={2}/>
          <text x="20" y="26" textAnchor="middle" fontSize="8" fontWeight="bold" fill={color}>LL</text>
        </svg>
      );
    case "dryer":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <circle cx="20" cy="22" r="8" fill="none" stroke={color} strokeWidth={2}/>
          <text x="20" y="26" textAnchor="middle" fontSize="8" fontWeight="bold" fill={color}>SL</text>
        </svg>
      );
    case "boiler":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="14" fill="white" stroke={color} strokeWidth={sw}/>
          <text x="20" y="25" textAnchor="middle" fontSize="14" fontWeight="bold" fill={color}>C</text>
        </svg>
      );
    case "convector":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="12" width="28" height="16" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <path d="M11 24 Q14 19 17 24 Q20 29 23 24 Q26 19 29 24" fill="none" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "towelwarmer":
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="6" y="8" width="28" height="24" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="12" y1="14" x2="28" y2="14" stroke={color} strokeWidth={2}/>
          <line x1="12" y1="20" x2="28" y2="20" stroke={color} strokeWidth={2}/>
          <line x1="12" y1="26" x2="28" y2="26" stroke={color} strokeWidth={2}/>
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
        width: 20,
        height: 20,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(255,255,255,0.6)",
        borderRadius: "50%",
        boxShadow: equipment.uncertain
          ? "0 0 0 3px rgba(255,152,0,0.85)"
          : "0 1px 2px rgba(0,0,0,0.15)",
      }}
      title={equipment.uncertain
        ? `${equipment.type} (${equipment.room}) — Placement auto à vérifier`
        : `${equipment.type} (${equipment.room})`}
    >
      <SvgEquipIcon svgId={svgId} color={equipment.color} size={14} />
    </div>
  );
});

/**
 * Chip palette équipement — drag-in actif depuis Phase 4.
 */
interface EquipmentPaletteChipProps {
  pt: EquipmentPaletteType;
  onDropOnCanvas: (
    pt: EquipmentPaletteType,
    clientX: number,
    clientY: number,
  ) => void;
}

const EquipmentPaletteChip = memo(function EquipmentPaletteChip({
  pt, onDropOnCanvas,
}: EquipmentPaletteChipProps) {
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

    const createGhost = (cx: number, cy: number) => {
      const g = document.createElement("div");
      g.style.cssText = `
        position: fixed; left: ${cx}px; top: ${cy}px;
        transform: translate(-50%, -50%);
        padding: 5px; border-radius: 50%;
        background: rgba(255,255,255,0.85);
        border: 2px dashed ${ptRef.current.color};
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 9999; pointer-events: none; opacity: 0.85;
      `;
      g.innerHTML = `<svg width="22" height="22" viewBox="0 0 40 40">
        <circle cx="20" cy="20" r="13" fill="white"
                stroke="${ptRef.current.color}" stroke-width="2.5"/>
      </svg>`;
      document.body.appendChild(g);
      return g;
    };

    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault(); e.stopPropagation();
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
      try { el.releasePointerCapture(e.pointerId); } catch {}
      if (ghost) { ghost.remove(); ghost = null; }
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      const finalX = e.clientX, finalY = e.clientY;
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
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "6px 10px",
        border: `2px solid ${pt.color}`, borderRadius: 18,
        background: "white", cursor: "grab", touchAction: "none",
        fontSize: 11, fontWeight: 600, color: "#333", whiteSpace: "nowrap",
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
    equip_visible_types,
    pastille_to_devis_room,
  } = typedArgs;

  const [pastilles, setPastilles] = useState<Pastille[]>(initial_pastilles ?? []);
  const [equipmentsState, setEquipmentsState] = useState<EquipmentInstance[]>(
    equipments ?? []
  );

  const imgRef = useRef<HTMLImageElement>(null);
  const lastSentJsonRef = useRef<string>("");

  // null/undefined → toutes les visible ; tableau (même vide) → filtre strict.
  const visibleTypesSet = useMemo(
    () => (equip_visible_types == null ? null : new Set(equip_visible_types)),
    [equip_visible_types]
  );
  const visibleEquipments = useMemo(
    () =>
      visibleTypesSet == null
        ? equipmentsState
        : equipmentsState.filter((e) => visibleTypesSet.has(e.type)),
    [visibleTypesSet, equipmentsState]
  );
  const showEquipPalette =
    visibleTypesSet == null || visibleTypesSet.size > 0;

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
  // Les pastilles existantes (même id) gardent leur position React mais
  // adoptent les attributs serveur (label, color, type) — utile pour les
  // re-labels d'indexation envoyés par Python après drag-in palette.
  useEffect(() => {
    const incoming = initial_pastilles ?? [];
    const incomingMap = new Map(incoming.map((p) => [String(p.id), p]));
    const incomingIds = new Set(incomingMap.keys());
    setPastilles((prev) => {
      const currentIds = new Set(prev.map((p) => String(p.id)));
      // Garde les pastilles "new_*" même absentes d'incoming : drag-in
      // palette pending que Python n'a pas encore acquitté. Sans cette
      // protection, boucle d'ajout/suppression avec indexes qui grimpent.
      const filtered = prev
        .filter(
          (p) => incomingIds.has(String(p.id))
            || String(p.id).startsWith("new_"),
        )
        .map((p) => {
          const fresh = incomingMap.get(String(p.id));
          if (
            fresh
            && (fresh.label !== p.label
              || fresh.color !== p.color
              || fresh.type !== p.type
              || fresh.rotation !== p.rotation)
          ) {
            // Server-controlled attrs mis à jour, x/y React préservés
            return {
              ...p,
              label: fresh.label,
              color: fresh.color,
              type: fresh.type,
              rotation: fresh.rotation,
            };
          }
          return p;
        });
      const added = incoming.filter((p) => !currentIds.has(String(p.id)));
      // Skip si pas de changement réel (même ids, mêmes attrs)
      if (
        added.length === 0
        && filtered.length === prev.length
        && filtered.every((p, i) => p === prev[i])
      ) {
        return prev;
      }
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
    // Rooms encore valides côté Python (i.e. au moins une pastille pièce
    // existe encore avec ce label). Une room qui disparaît de la map signe
    // un drag-out de pastille pièce → les équipements "new_*" rattachés à
    // cette room sont devenus orphelins, on les drop aussi.
    const validRooms = new Set(
      Object.values(pastille_to_devis_room ?? {}),
    );
    setEquipmentsState((prev) => {
      const currentIds = new Set(prev.map((e) => e.id));
      if (incomingIds.size === currentIds.size
          && [...incomingIds].every((id) => currentIds.has(id))) {
        return prev;
      }
      // Garde les équipements "new_*" même absents d'incoming : ajout
      // palette pending que Python n'a pas encore acquitté.
      // MAIS : si la room de l'équipement n'est plus valide (pastille pièce
      // drag-outée), drop quand même — sinon les "new_*" deviennent des
      // orphelins jamais supprimables par Python.
      const filtered = prev.filter((e) => {
        if (incomingIds.has(e.id)) return true;
        if (!e.id.startsWith("new_")) return false;
        return validRooms.has(e.room);
      });
      const added = incoming.filter((e) => !currentIds.has(e.id));
      return [...filtered, ...added];
    });
  }, [equipments, pastille_to_devis_room]);

  // Handler drop équipement existant (commit position ou suppression hors plan).
  // Drag = validation manuelle → efface uncertain pour que le halo disparaisse.
  // La valeur updated est incluse dans le payload envoyé à Python via l'effet
  // setComponentValue (equipmentsState), donc Python voit uncertain=false après
  // un drag.
  const handleEquipmentDrop = useCallback(
    (id: string, drop: EquipDropResult) => {
      if (!drop.insideImage) {
        setEquipmentsState((prev) => prev.filter((e) => e.id !== id));
      } else {
        setEquipmentsState((prev) =>
          prev.map((e) =>
            e.id === id
              ? { ...e, x: drop.finalImgX, y: drop.finalImgY, uncertain: false }
              : e,
          ),
        );
      }
    },
    [],
  );

  // Handler drop depuis palette équipement (ajout instance équipement)
  const handlePaletteEquipDrop = useCallback(
    (pt: EquipmentPaletteType, clientX: number, clientY: number) => {
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
      let closestPastilleId = "";
      let closestPastilleLabel = "";
      let minDist = Infinity;
      for (const p of pastilles) {
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < minDist) {
          minDist = d;
          closestPastilleId = String(p.id);
          closestPastilleLabel = p.label;
        }
      }
      // Le devis utilise des labels NFCCategory-indexés ("Chambre 1",
      // "Chambre 2"…) alors que les pastilles portent le label FR brut
      // ("Chambre"). Traduit via la map fournie par Python pour que le
      // sync block trouve la bonne ligne devis.
      const devisRoom = (
        pastille_to_devis_room?.[closestPastilleId]
        ?? closestPastilleLabel
        ?? "Autre"
      );
      const newId = `new_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      setEquipmentsState((prev) => [
        ...prev,
        {
          id: newId,
          type: pt.type,
          room: devisRoom,
          x, y,
          color: pt.color,
        },
      ]);
    },
    [image_width, image_height, pastilles, pastille_to_devis_room],
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
        {visibleEquipments.length > 0 && visibleEquipments.map((eq) => (
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

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="pc-palette">
          <div className="pc-palette-title">Pièces</div>
          {palette.map((pt) => (
            <PaletteChip
              key={pt.type}
              pt={pt}
              onDropOnCanvas={handlePaletteDrop}
            />
          ))}
        </div>

        {showEquipPalette && equip_palette && equip_palette.length > 0 && (
          <div className="pc-palette">
            <div className="pc-palette-title">Équipements</div>
            {equip_palette.map((pt) => (
              <EquipmentPaletteChip
                key={pt.type}
                pt={pt}
                onDropOnCanvas={handlePaletteEquipDrop}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default withStreamlitConnection(PastilleCanvas);
