import type { ImageDimensions, Region } from "./types";

export const MAX_REGIONS = 20;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function clampRegion(region: Region, image: ImageDimensions): Region {
  const x = clamp(Math.round(region.x), 0, Math.max(0, image.width - 1));
  const y = clamp(Math.round(region.y), 0, Math.max(0, image.height - 1));
  const width = clamp(Math.round(region.width), 1, Math.max(1, image.width - x));
  const height = clamp(Math.round(region.height), 1, Math.max(1, image.height - y));
  return { ...region, x, y, width, height };
}

export function regionFromPoints(
  id: string,
  start: { x: number; y: number },
  end: { x: number; y: number },
  image: ImageDimensions
): Region {
  return clampRegion(
    {
      id,
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      width: Math.max(1, Math.abs(end.x - start.x)),
      height: Math.max(1, Math.abs(end.y - start.y))
    },
    image
  );
}

export function clientPointToImage(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, "left" | "top" | "width" | "height">,
  image: ImageDimensions
) {
  return {
    x: clamp(((clientX - bounds.left) / bounds.width) * image.width, 0, image.width),
    y: clamp(((clientY - bounds.top) / bounds.height) * image.height, 0, image.height)
  };
}

export function serializeRegions(regions: Region[]) {
  return JSON.stringify(regions.map(({ x, y, width, height }) => ({ x, y, width, height })));
}
