import { describe, expect, it } from "vitest";
import { clampRegion, clientPointToImage, MAX_REGIONS, regionFromPoints, serializeRegions } from "./regions";

const image = { width: 1000, height: 500 };

describe("region geometry", () => {
  it("maps display coordinates to original pixels", () => {
    expect(clientPointToImage(150, 75, { left: 50, top: 25, width: 500, height: 250 }, image)).toEqual({
      x: 200,
      y: 100
    });
  });

  it("creates a normalized region when dragging backwards", () => {
    expect(regionFromPoints("a", { x: 700, y: 350 }, { x: 100, y: 50 }, image)).toEqual({
      id: "a",
      x: 100,
      y: 50,
      width: 600,
      height: 300
    });
  });

  it("clamps coordinates and dimensions to the image", () => {
    expect(clampRegion({ id: "a", x: 990, y: -10, width: 100, height: 999 }, image)).toEqual({
      id: "a",
      x: 990,
      y: 0,
      width: 10,
      height: 500
    });
  });

  it("serializes only API fields", () => {
    expect(serializeRegions([{ id: "private", x: 1, y: 2, width: 3, height: 4 }])).toBe(
      '[{"x":1,"y":2,"width":3,"height":4}]'
    );
    expect(MAX_REGIONS).toBe(20);
  });
});
