import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, authenticate, getJob, identify, processBinary, submitGpuJob } from "./api";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("API client", () => {
  it("sends the API key only in the authentication header", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ customer_id: "c", customer_name: "Client", external_id: null, key_id: "k", key_prefix: "abc" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    const key = "raiw_123456789abc_super-secret";
    await authenticate(key);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/me");
    expect(String(url)).not.toContain(key);
    expect(init?.headers).toEqual({ "X-API-Key": key });
    expect(localStorage.length).toBe(0);
  });

  it("omits the authentication header in anonymous mode", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          customer_id: "00000000-0000-0000-0000-000000000000",
          customer_name: "Anonymous API Client",
          external_id: "anonymous",
          key_id: null,
          key_prefix: null
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );
    await authenticate("");
    expect(fetchMock.mock.calls[0]).toEqual(["/api/v1/me", { headers: {} }]);
  });

  it("builds multipart requests without overriding the content type", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ request_id: "r", archive_id: "a", report: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    await identify(new File(["image"], "image.png", { type: "image/png" }), "key");
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.body).toBeInstanceOf(FormData);
    expect(init?.headers).toEqual({ "X-API-Key": "key" });
  });

  it("returns binary result identifiers and filename", async () => {
    fetchMock.mockResolvedValue(
      new Response(new Blob(["processed"], { type: "image/png" }), {
        status: 200,
        headers: {
          "Content-Disposition": 'attachment; filename="processed.png"',
          "X-Request-ID": "request-1",
          "X-Archive-ID": "archive-1"
        }
      })
    );
    const result = await processBinary(
      "/api/v1/remove/metadata",
      new File(["image"], "image.png"),
      "key",
      { keep_standard: true }
    );
    expect(result.filename).toBe("processed.png");
    expect(result.requestId).toBe("request-1");
    expect(result.archiveId).toBe("archive-1");
  });

  it("preserves structured API errors", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "no_visible_mark", message: "none", details: null, request_id: "request-2" } }),
        { status: 422, headers: { "Content-Type": "application/json" } }
      )
    );
    await expect(
      processBinary("/api/v1/remove/visible", new File(["image"], "image.png"), "key", {})
    ).rejects.toMatchObject({ code: "no_visible_mark", requestId: "request-2", status: 422 } satisfies Partial<ApiError>);
  });

  it("encodes job ids and supports GPU submission", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "id/one", archive_id: "a", status: "queued", status_url: "s", result_url: "r" }), {
          status: 202,
          headers: { "Content-Type": "application/json" }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "id/one", archive_id: "a", task_name: "all", status: "queued", progress: 0, created_at: "now", updated_at: "now" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      );
    await submitGpuJob("all", new File(["image"], "image.png"), "key", { steps: 20 });
    await getJob("id/one", "key");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/jobs/all");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/jobs/id%2Fone");
  });
});
