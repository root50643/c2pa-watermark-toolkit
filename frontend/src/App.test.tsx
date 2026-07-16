import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { API_KEY_SESSION_KEY } from "./api";

const api = vi.hoisted(() => ({
  authenticate: vi.fn(),
  getCapabilities: vi.fn(),
  getReady: vi.fn(),
  identify: vi.fn(),
  processBinary: vi.fn(),
  submitGpuJob: vi.fn(),
  getJob: vi.fn(),
  downloadJobResult: vi.fn(),
  downloadBlob: vi.fn()
}));

vi.mock("./api", async (original) => {
  const actual = await original<typeof import("./api")>();
  return { ...actual, ...api };
});

beforeEach(() => {
  vi.clearAllMocks();
  api.getCapabilities.mockResolvedValue({
    app_version: "0.1.0",
    upstream_version: "0.15.3",
    supported_formats: ["png", "jpeg", "webp", "heic", "heif", "avif"],
    max_upload_mb: 25,
    max_image_pixels: 50_000_000,
    archive_ready: true,
    redis_ready: false,
    visible_backends: ["cv2", "migan", "lama"],
    gpu_pipelines: ["controlnet", "sdxl", "qwen"]
  });
  api.getReady.mockResolvedValue({ status: "ready", archive: true, database: true });
  api.authenticate.mockResolvedValue({
    customer_id: "customer-1",
    customer_name: "Demo Client",
    external_id: null,
    key_id: "key-1",
    key_prefix: "123456789abc"
  });
  api.identify.mockResolvedValue({ request_id: "request-1", archive_id: "archive-1", report: { source: "local" } });
  api.processBinary.mockResolvedValue({
    blob: new Blob(["processed"], { type: "image/png" }),
    filename: "processed.png",
    requestId: "request-2",
    archiveId: "archive-2",
    removedMarks: null
  });
  api.submitGpuJob.mockResolvedValue({
    job_id: "job-1",
    archive_id: "archive-3",
    status: "queued",
    status_url: "/api/v1/jobs/job-1",
    result_url: "/api/v1/jobs/job-1/result"
  });
  api.getJob.mockResolvedValue({
    job_id: "job-1",
    archive_id: "archive-3",
    task_name: "invisible",
    status: "queued",
    progress: 0,
    message: null,
    error: null,
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
    result_url: null
  });
});

describe("workbench", () => {
  it("starts in Traditional Chinese and switches to English", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(API_KEY_SESSION_KEY, "key");
    render(<App />);
    await screen.findByText("Demo Client");
    expect(screen.getByRole("heading", { name: "AI 浮水印處理工作台", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "移除 Metadata" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByRole("heading", { name: "AI Watermark Processing Workbench", level: 1 })).toBeInTheDocument();
    expect(localStorage.getItem("raiw_locale")).toBe("en");
  });

  it("connects with a customer key and stores it only for the session", async () => {
    const user = userEvent.setup();
    render(<App />);
    const key = "raiw_123456789abc_super-secret";
    await user.type(screen.getByLabelText("API Key"), key);
    await user.click(screen.getByRole("button", { name: "連接" }));
    await screen.findByText("Demo Client");
    expect(api.authenticate).toHaveBeenCalledWith(key);
    expect(sessionStorage.getItem(API_KEY_SESSION_KEY)).toBe(key);
    expect(localStorage.getItem(API_KEY_SESSION_KEY)).toBeNull();
    expect(window.location.href).not.toContain(key);
  });

  it("does not render client-facing data policy messages", async () => {
    render(<App />);
    await waitFor(() => expect(api.getCapabilities).toHaveBeenCalled());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/永久保存|IP 位址|稽核|retention|audit/i);
  });

  it("rejects an unsupported file before sending it", async () => {
    sessionStorage.setItem(API_KEY_SESSION_KEY, "key");
    render(<App />);
    await screen.findByText("Demo Client");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["gif"], "image.gif", { type: "image/gif" })] } });
    expect(await screen.findByText("不支援這個檔案格式。")).toBeInTheDocument();
    expect(api.identify).not.toHaveBeenCalled();
  });

  it("submits identification and displays request identifiers", async () => {
    sessionStorage.setItem(API_KEY_SESSION_KEY, "key");
    render(<App />);
    await screen.findByText("Demo Client");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["png"], "image.png", { type: "image/png" })] } });
    await userEvent.click(screen.getByRole("tab", { name: "圖片識別" }));
    await userEvent.click(screen.getByRole("button", { name: "開始處理" }));
    expect(api.identify).toHaveBeenCalledWith(expect.any(File), "key");
    expect(await screen.findByText("request-1")).toBeInTheDocument();
    expect(screen.getByText("archive-1")).toBeInTheDocument();
  });

  it("submits visible and metadata binary workflows", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(API_KEY_SESSION_KEY, "key");
    render(<App />);
    await screen.findByText("Demo Client");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["png"], "image.png", { type: "image/png" })] } });

    await user.click(screen.getByRole("tab", { name: "移除可見標記" }));
    await user.click(screen.getByRole("button", { name: "開始處理" }));
    expect(api.processBinary).toHaveBeenLastCalledWith(
      "/api/v1/remove/visible",
      expect.any(File),
      "key",
      expect.objectContaining({ sensitivity: "auto", backend: "cv2", strip_metadata: true })
    );

    await user.click(screen.getByRole("tab", { name: "移除 Metadata" }));
    await user.click(screen.getByRole("button", { name: "開始處理" }));
    expect(api.processBinary).toHaveBeenLastCalledWith(
      "/api/v1/remove/metadata",
      expect.any(File),
      "key",
      { keep_standard: true }
    );
  });

  it("submits and tracks a GPU job when the queue is available", async () => {
    const user = userEvent.setup();
    api.getCapabilities.mockResolvedValueOnce({
      ...(await api.getCapabilities()),
      redis_ready: true
    });
    sessionStorage.setItem(API_KEY_SESSION_KEY, "key");
    render(<App />);
    await screen.findByText("Demo Client");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["png"], "image.png", { type: "image/png" })] } });
    await user.click(screen.getByRole("tab", { name: /不可見浮水印/ }));
    await user.click(screen.getByRole("button", { name: "開始處理" }));
    await waitFor(() => expect(api.submitGpuJob).toHaveBeenCalledWith("invisible", expect.any(File), "key", expect.objectContaining({ pipeline: "controlnet", steps: 50 })));
    expect(await screen.findByText("job-1")).toBeInTheDocument();
  });
});
