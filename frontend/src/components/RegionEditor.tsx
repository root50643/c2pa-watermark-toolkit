import { Maximize2, Trash2 } from "lucide-react";
import { useRef, useState, type PointerEvent } from "react";
import type { MessageKey } from "../i18n";
import { clampRegion, clientPointToImage, MAX_REGIONS, regionFromPoints } from "../regions";
import type { ImageDimensions, Region } from "../types";

interface RegionEditorProps {
  imageUrl: string;
  dimensions: ImageDimensions;
  regions: Region[];
  onChange: (regions: Region[]) => void;
  t: (key: MessageKey) => string;
}

export function RegionEditor({ imageUrl, dimensions, regions, onChange, t }: RegionEditorProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<Region | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const point = (event: PointerEvent<HTMLDivElement>) => {
    const bounds = stageRef.current?.getBoundingClientRect();
    return bounds ? clientPointToImage(event.clientX, event.clientY, bounds, dimensions) : null;
  };

  const begin = (event: PointerEvent<HTMLDivElement>) => {
    if (regions.length >= MAX_REGIONS) return;
    const origin = point(event);
    if (!origin) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedId(null);
    setStart(origin);
    setDraft(regionFromPoints("draft", origin, origin, dimensions));
  };

  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!start) return;
    const current = point(event);
    if (current) setDraft(regionFromPoints("draft", start, current, dimensions));
  };

  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (draft && draft.width >= 3 && draft.height >= 3) {
      const next = { ...draft, id: crypto.randomUUID() };
      onChange([...regions, next].slice(0, MAX_REGIONS));
      setSelectedId(next.id);
    }
    setStart(null);
    setDraft(null);
  };

  const update = (id: string, key: "x" | "y" | "width" | "height", value: number) => {
    onChange(regions.map((region) => (region.id === id ? clampRegion({ ...region, [key]: value }, dimensions) : region)));
  };

  const remove = (id: string) => {
    onChange(regions.filter((region) => region.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const regionStyle = (region: Region) => ({
    left: `${(region.x / dimensions.width) * 100}%`,
    top: `${(region.y / dimensions.height) * 100}%`,
    width: `${(region.width / dimensions.width) * 100}%`,
    height: `${(region.height / dimensions.height) * 100}%`
  });

  return (
    <div className="region-editor">
      <div className="region-toolbar">
        <span><Maximize2 size={16} /> {t("drawRegion")}</span>
        <span className="region-counter">{regions.length}/{MAX_REGIONS}</span>
        {regions.length > 0 && (
          <button className="text-action" type="button" onClick={() => onChange([])}>{t("clearRegions")}</button>
        )}
      </div>
      <div
        ref={stageRef}
        className="region-stage"
        onPointerDown={begin}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={finish}
        onKeyDown={(event) => {
          if ((event.key === "Delete" || event.key === "Backspace") && selectedId) remove(selectedId);
        }}
        tabIndex={0}
        aria-label={t("drawRegion")}
      >
        <img src={imageUrl} alt={t("imagePreview")} draggable="false" />
        {[...regions, ...(draft ? [draft] : [])].map((region, index) => (
          <button
            key={region.id}
            className={`region-box ${selectedId === region.id ? "selected" : ""} ${region.id === "draft" ? "draft" : ""}`}
            style={regionStyle(region)}
            type="button"
            aria-label={`${t("region")} ${index + 1}`}
            onPointerDown={(event) => {
              event.stopPropagation();
              if (region.id !== "draft") setSelectedId(region.id);
            }}
          >
            <span>{index + 1}</span>
          </button>
        ))}
      </div>
      {regions.length >= MAX_REGIONS && <p className="field-error">{t("regionLimit")}</p>}
      {regions.length > 0 && (
        <div className="region-list">
          {regions.map((region, index) => (
            <div className={`region-row ${selectedId === region.id ? "selected" : ""}`} key={region.id}>
              <button type="button" className="region-number" onClick={() => setSelectedId(region.id)}>{index + 1}</button>
              {(["x", "y", "width", "height"] as const).map((key) => (
                <label key={key}>
                  <span>{t(key)}</span>
                  <input
                    type="number"
                    min={key === "width" || key === "height" ? 1 : 0}
                    value={region[key]}
                    onFocus={() => setSelectedId(region.id)}
                    onChange={(event) => update(region.id, key, Number(event.target.value))}
                  />
                </label>
              ))}
              <button className="icon-button danger" type="button" onClick={() => remove(region.id)} aria-label={t("removeRegion")}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
