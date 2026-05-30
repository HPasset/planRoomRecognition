import { useEffect, useRef, useState, useCallback, memo } from "react";
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

interface Args {
  image_data: string;
  image_width: number;
  image_height: number;
  initial_pastilles: Pastille[];
  palette: PaletteType[];
  seg_polygons?: SegPolygon[];
  yolo_boxes?: YoloBox[];
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
  } = typedArgs;

  const [pastilles, setPastilles] = useState<Pastille[]>(initial_pastilles ?? []);

  const imgRef = useRef<HTMLImageElement>(null);
  const lastSentJsonRef = useRef<string>("");

  // setFrameHeight : seulement quand contenu change vraiment
  useEffect(() => {
    Streamlit.setFrameHeight();
  }, [pastilles.length, palette.length, image_data]);

  // Notify Python à chaque changement réel de pastilles
  useEffect(() => {
    const json = JSON.stringify(pastilles);
    if (json === lastSentJsonRef.current) return;
    lastSentJsonRef.current = json;
    Streamlit.setComponentValue({ pastilles });
  }, [pastilles]);

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
      </div>

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
