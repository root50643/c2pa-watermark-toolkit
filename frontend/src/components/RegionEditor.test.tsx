import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { translate } from "../i18n";
import { RegionEditor } from "./RegionEditor";

describe("RegionEditor", () => {
  it("draws a region using original-image coordinates", () => {
    const onChange = vi.fn();
    const randomUUID = vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
    render(
      <RegionEditor
        imageUrl="blob:test"
        dimensions={{ width: 1000, height: 500 }}
        regions={[]}
        onChange={onChange}
        t={(key) => translate("en", key)}
      />
    );
    const stage = screen.getByLabelText("Drag on the image to add a repair region");
    Object.defineProperty(stage, "getBoundingClientRect", {
      value: () => ({ left: 0, top: 0, width: 500, height: 250, right: 500, bottom: 250, x: 0, y: 0, toJSON: () => ({}) })
    });
    Object.defineProperty(stage, "setPointerCapture", { value: vi.fn() });
    Object.defineProperty(stage, "hasPointerCapture", { value: () => true });
    Object.defineProperty(stage, "releasePointerCapture", { value: vi.fn() });

    fireEvent.pointerDown(stage, { pointerId: 1, clientX: 50, clientY: 25 });
    fireEvent.pointerMove(stage, { pointerId: 1, clientX: 150, clientY: 75 });
    fireEvent.pointerUp(stage, { pointerId: 1, clientX: 150, clientY: 75 });

    expect(onChange).toHaveBeenCalledWith([
      { id: "00000000-0000-4000-8000-000000000001", x: 100, y: 50, width: 200, height: 100 }
    ]);
    randomUUID.mockRestore();
  });
});
