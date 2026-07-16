import {
  Activity,
  Braces,
  Check,
  CircleAlert,
  Eraser,
  Eye,
  FileImage,
  Layers3,
  LoaderCircle,
  Menu,
  ScanSearch,
  Sparkles,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_KEY_SESSION_KEY,
  ApiError,
  JOBS_SESSION_KEY,
  authenticate,
  downloadBlob,
  downloadJobResult,
  getCapabilities,
  getJob,
  getReady,
  identify,
  processBinary,
  submitGpuJob
} from "./api";
import { ConnectionPanel } from "./components/ConnectionPanel";
import { JobsPanel } from "./components/JobsPanel";
import { RegionEditor } from "./components/RegionEditor";
import { ResultPanel } from "./components/ResultPanel";
import { SystemStatus } from "./components/SystemStatus";
import { UploadZone } from "./components/UploadZone";
import { translate, type MessageKey } from "./i18n";
import { serializeRegions } from "./regions";
import type {
  BinaryResult,
  Capabilities,
  Customer,
  IdentifyResult,
  ImageDimensions,
  Locale,
  Operation,
  Region,
  TrackedJob
} from "./types";
import "./styles.css";

const operations: Array<{
  id: Operation;
  title: MessageKey;
  description: MessageKey;
  icon: typeof Eye;
  gpu?: boolean;
}> = [
  { id: "metadata", title: "metadata", description: "metadataDescription", icon: Braces },
  { id: "identify", title: "identify", description: "identifyDescription", icon: ScanSearch },
  { id: "visible", title: "visible", description: "visibleDescription", icon: Eye },
  { id: "erase", title: "erase", description: "eraseDescription", icon: Eraser },
  { id: "invisible", title: "invisible", description: "invisibleDescription", icon: Sparkles, gpu: true },
  { id: "all", title: "all", description: "allDescription", icon: Layers3, gpu: true }
];

interface UiError {
  message: string;
  code?: string;
  requestId?: string | null;
}

function initialJobs(): TrackedJob[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(JOBS_SESSION_KEY) ?? "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is TrackedJob =>
        typeof item === "object" && item !== null && typeof (item as TrackedJob).jobId === "string"
    );
  } catch {
    return [];
  }
}

function operationFields(operation: Operation): Record<string, string | number | boolean> {
  switch (operation) {
    case "visible":
      return { sensitivity: "auto", backend: "cv2", strip_metadata: true };
    case "erase":
      return { backend: "cv2", method: "telea", dilate: 3, strip_metadata: true };
    case "metadata":
      return { keep_standard: true };
    case "invisible":
    case "all":
      return {
        pipeline: "controlnet",
        strength: "",
        steps: 50,
        seed: "",
        force: false,
        max_resolution: 0,
        min_resolution: 1024,
        tile: false,
        tile_size: 1024,
        tile_overlap: 128,
        sensitivity: "auto",
        backend: "cv2"
      };
    default:
      return {};
  }
}

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => (localStorage.getItem("raiw_locale") === "en" ? "en" : "zh-TW"));
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [ready, setReady] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem(API_KEY_SESSION_KEY) ?? "");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [operation, setOperation] = useState<Operation>("metadata");
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState<ImageDimensions | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [fields, setFields] = useState<Record<string, string | number | boolean>>(operationFields("metadata"));
  const [processing, setProcessing] = useState(false);
  const [binaryResult, setBinaryResult] = useState<BinaryResult | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [resultSourceUrl, setResultSourceUrl] = useState<string | null>(null);
  const [identifyResult, setIdentifyResult] = useState<IdentifyResult | null>(null);
  const [jobs, setJobs] = useState<TrackedJob[]>(initialJobs);
  const [busyJob, setBusyJob] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);

  const t = useCallback((key: MessageKey) => translate(locale, key), [locale]);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-Hant";
    localStorage.setItem("raiw_locale", locale);
  }, [locale]);

  const refreshStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const [nextCapabilities, nextReady] = await Promise.all([getCapabilities(), getReady()]);
      setCapabilities(nextCapabilities);
      setReady(nextReady.status === "ready");
    } catch {
      setReady(false);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const explainError = useCallback(
    (caught: unknown): UiError => {
      if (!(caught instanceof ApiError)) return { message: t("requestFailed") };
      const messages: Record<string, MessageKey> = {
        missing_api_key: "invalidKey",
        invalid_api_key: "invalidKey",
        no_visible_mark: "noVisibleMark",
        gpu_worker_unavailable: "gpuWorkerUnavailable",
        queue_failed: "gpuWorkerUnavailable",
        invalid_regions: "invalidRegions",
        upload_too_large: "uploadTooLarge",
        image_too_large: "uploadTooLarge",
        unsupported_media_type: "unsupportedMedia"
      };
      return {
        message: messages[caught.code] ? t(messages[caught.code]) : caught.message || t("requestFailed"),
        code: caught.code,
        requestId: caught.requestId
      };
    },
    [t]
  );

  const connect = useCallback(
    async (key: string) => {
      setAuthLoading(true);
      setError(null);
      try {
        const nextCustomer = await authenticate(key);
        sessionStorage.setItem(API_KEY_SESSION_KEY, key);
        setApiKey(key);
        setCustomer(nextCustomer);
      } catch (caught) {
        sessionStorage.removeItem(API_KEY_SESSION_KEY);
        setApiKey("");
        setCustomer(null);
        setError(explainError(caught));
      } finally {
        setAuthLoading(false);
      }
    },
    [explainError]
  );

  useEffect(() => {
    if (apiKey && !customer) void connect(apiKey);
  }, [apiKey, connect, customer]);

  const disconnect = () => {
    sessionStorage.removeItem(API_KEY_SESSION_KEY);
    sessionStorage.removeItem(JOBS_SESSION_KEY);
    setApiKey("");
    setCustomer(null);
    setJobs([]);
    setError(null);
  };

  useEffect(() => {
    if (!file) {
      setSourceUrl(null);
      setDimensions(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setSourceUrl(url);
    setDimensions(null);
    const image = new Image();
    image.onload = () => setDimensions({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => setDimensions(null);
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!binaryResult) {
      setResultUrl(null);
      return;
    }
    const url = URL.createObjectURL(binaryResult.blob);
    setResultUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [binaryResult]);

  useEffect(() => {
    sessionStorage.setItem(
      JOBS_SESSION_KEY,
      JSON.stringify(
        jobs.map((job) => ({
          jobId: job.jobId,
          archiveId: job.archiveId,
          taskName: job.taskName,
          createdAt: job.createdAt
        }))
      )
    );
  }, [jobs]);

  const activeJobIds = useMemo(
    () => jobs.filter((job) => !job.status || !["succeeded", "failed"].includes(job.status.status)).map((job) => job.jobId),
    [jobs]
  );
  const activeJobKey = activeJobIds.join(",");

  const refreshJob = useCallback(
    async (jobId: string) => {
      if (!apiKey) return;
      try {
        const status = await getJob(jobId, apiKey);
        setJobs((current) => current.map((job) => (job.jobId === jobId ? { ...job, status, pollingError: undefined } : job)));
      } catch (caught) {
        const message = explainError(caught).message;
        setJobs((current) => current.map((job) => (job.jobId === jobId ? { ...job, pollingError: message } : job)));
      }
    },
    [apiKey, explainError]
  );

  useEffect(() => {
    if (!apiKey || !activeJobKey) return;
    let cancelled = false;
    let timer: number | undefined;
    const jobIds = activeJobKey.split(",").filter(Boolean);
    const poll = async () => {
      await Promise.all(jobIds.map((jobId) => refreshJob(jobId)));
      if (!cancelled) timer = window.setTimeout(poll, document.hidden ? 10_000 : 2_000);
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeJobKey, apiKey, refreshJob]);

  const chooseOperation = (next: Operation) => {
    setOperation(next);
    setFields(operationFields(next));
    setRegions([]);
    setError(null);
  };

  const chooseFile = (next: File) => {
    const format = next.name.split(".").pop()?.toLowerCase().replace("jpg", "jpeg") ?? "";
    const accepted = capabilities?.supported_formats ?? ["png", "jpeg", "webp", "heic", "heif", "avif"];
    if (!accepted.includes(format)) {
      setError({ message: t("invalidFileType") });
      return;
    }
    if (next.size > (capabilities?.max_upload_mb ?? 25) * 1024 * 1024) {
      setError({ message: t("fileTooLarge") });
      return;
    }
    setFile(next);
    setRegions([]);
    setBinaryResult(null);
    setIdentifyResult(null);
    setResultSourceUrl(null);
    setError(null);
  };

  const updateField = (name: string, value: string | number | boolean) => {
    setFields((current) => ({ ...current, [name]: value }));
  };

  const runOperation = async () => {
    if (!file || !apiKey) {
      setError({ message: t("missingFile") });
      return;
    }
    if (operation === "erase" && regions.length === 0) {
      setError({ message: t("missingRegions") });
      return;
    }
    setProcessing(true);
    setError(null);
    setBinaryResult(null);
    setIdentifyResult(null);
    setResultSourceUrl(null);
    try {
      if (operation === "identify") {
        setIdentifyResult(await identify(file, apiKey));
      } else if (operation === "visible") {
        const result = await processBinary("/api/v1/remove/visible", file, apiKey, fields);
        setBinaryResult(result);
        setResultSourceUrl(sourceUrl);
      } else if (operation === "erase") {
        const result = await processBinary("/api/v1/remove/erase", file, apiKey, {
          ...fields,
          regions: serializeRegions(regions)
        });
        setBinaryResult(result);
        setResultSourceUrl(sourceUrl);
      } else if (operation === "metadata") {
        const result = await processBinary("/api/v1/remove/metadata", file, apiKey, fields);
        setBinaryResult(result);
        setResultSourceUrl(sourceUrl);
      } else {
        const gpuFields = { ...fields };
        if (operation === "invisible") {
          delete gpuFields.sensitivity;
          delete gpuFields.backend;
        }
        const accepted = await submitGpuJob(operation, file, apiKey, gpuFields);
        setJobs((current) => [
          {
            jobId: accepted.job_id,
            archiveId: accepted.archive_id,
            taskName: operation,
            createdAt: new Date().toISOString()
          },
          ...current.filter((job) => job.jobId !== accepted.job_id)
        ]);
        window.setTimeout(() => document.getElementById("jobs")?.scrollIntoView({ behavior: "smooth" }), 0);
      }
    } catch (caught) {
      setError(explainError(caught));
    } finally {
      setProcessing(false);
    }
  };

  const fetchJobResult = async (job: TrackedJob) => {
    if (!apiKey) return;
    setBusyJob(job.jobId);
    setError(null);
    try {
      const result = await downloadJobResult(job.jobId, apiKey);
      downloadBlob(result.blob, result.filename);
    } catch (caught) {
      setError(explainError(caught));
    } finally {
      setBusyJob(null);
    }
  };

  const currentOperation = operations.find((item) => item.id === operation) ?? operations[0];
  const gpuDisabled = Boolean(currentOperation.gpu && !capabilities?.redis_ready);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label={t("appName")}>
          <span className="brand-mark"><Activity size={19} /></span>
          <span><strong>RAIW</strong><small>STUDIO</small></span>
        </a>
        <nav className={mobileMenu ? "open" : ""} aria-label="Primary">
          <a href="#workspace" onClick={() => setMobileMenu(false)}>{t("navigationWorkspace")}</a>
          <a href="#jobs" onClick={() => setMobileMenu(false)}>{t("navigationJobs")}</a>
        </nav>
        <div className="topbar-actions">
          <div className="locale-switch" aria-label={t("language")}>
            <button className={locale === "zh-TW" ? "active" : ""} type="button" onClick={() => setLocale("zh-TW")}>中</button>
            <button className={locale === "en" ? "active" : ""} type="button" onClick={() => setLocale("en")}>EN</button>
          </div>
          <button className="menu-button" type="button" onClick={() => setMobileMenu((current) => !current)} aria-label="Menu">
            <Menu size={20} />
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy">
            <div className="hero-kicker"><Sparkles size={14} /> IMAGE INTELLIGENCE</div>
            <h1>{t("appName")}</h1>
            <p>{t("appSubtitle")}</p>
          </div>
          <SystemStatus capabilities={capabilities} ready={ready} loading={statusLoading} onRefresh={refreshStatus} t={t} />
        </section>

        <ConnectionPanel customer={customer} loading={authLoading} onConnect={connect} onDisconnect={disconnect} t={t} />

        {customer && (
          <>
            <section className="workspace-section" id="workspace">
              <div className="section-heading workspace-heading">
                <span className="eyebrow">WORKBENCH</span>
                <h2>{t("workspace")}</h2>
                <p>{t("chooseAction")}</p>
              </div>

              <div className="operation-tabs" role="tablist" aria-label={t("chooseAction")}>
                {operations.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="tab"
                      aria-selected={operation === item.id}
                      className={operation === item.id ? "active" : ""}
                      onClick={() => chooseOperation(item.id)}
                    >
                      <Icon size={19} />
                      <span>{t(item.title)}</span>
                      {item.gpu && <i>GPU</i>}
                    </button>
                  );
                })}
              </div>

              <div className="processing-grid">
                <section className="source-card">
                  <UploadZone file={file} maxMb={capabilities?.max_upload_mb ?? 25} onFile={chooseFile} t={t} />
                  {file && sourceUrl && (
                    operation === "erase" ? (
                      dimensions ? (
                        <RegionEditor imageUrl={sourceUrl} dimensions={dimensions} regions={regions} onChange={setRegions} t={t} />
                      ) : (
                        <div className="preview-message"><CircleAlert size={20} /><p>{t("regionPreviewRequired")}</p></div>
                      )
                    ) : (
                      <div className="source-preview">
                        {dimensions ? (
                          <img src={sourceUrl} alt={t("imagePreview")} />
                        ) : (
                          <div className="preview-message"><FileImage size={24} /><p>{t("previewUnavailable")}</p></div>
                        )}
                        <div className="file-meta">
                          <span>{t("selectedFile")} <strong>{file.name}</strong></span>
                          {dimensions && <span>{t("imageDimensions")} <strong>{dimensions.width} × {dimensions.height} {t("pixels")}</strong></span>}
                        </div>
                      </div>
                    )
                  )}
                </section>

                <section className="settings-card">
                  <div className="settings-heading">
                    <div className="operation-icon"><currentOperation.icon size={22} /></div>
                    <div><h3>{t(currentOperation.title)}</h3><p>{t(currentOperation.description)}</p></div>
                  </div>
                  <SettingsForm operation={operation} fields={fields} updateField={updateField} t={t} />
                  {gpuDisabled && <div className="inline-warning"><CircleAlert size={17} /><span>{t("gpuUnavailable")}</span></div>}
                  <button
                    className="button primary process-button"
                    type="button"
                    disabled={!file || processing || gpuDisabled || (operation === "erase" && !dimensions)}
                    onClick={() => void runOperation()}
                  >
                    {processing ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
                    {processing ? t("processing") : t("run")}
                  </button>
                </section>
              </div>
            </section>

            <ResultPanel
              sourceUrl={resultSourceUrl}
              resultUrl={resultUrl}
              binary={binaryResult}
              report={identifyResult}
              onDownload={() => binaryResult && downloadBlob(binaryResult.blob, binaryResult.filename)}
              t={t}
            />

            <div id="jobs">
              <JobsPanel
                jobs={jobs}
                locale={locale}
                busyJob={busyJob}
                onDownload={(job) => void fetchJobResult(job)}
                onRefresh={(jobId) => void refreshJob(jobId)}
                onClearFinished={() => setJobs((current) => current.filter((job) => !job.status || !["succeeded", "failed"].includes(job.status.status)))}
                t={t}
              />
            </div>
          </>
        )}
      </main>

      <footer><span>RAIW Studio</span><span>FastAPI · React · Docker</span></footer>

      {error && (
        <div className="toast" role="alert">
          <div className="toast-icon"><CircleAlert size={20} /></div>
          <div><strong>{t("errorTitle")}</strong><p>{error.message}</p>{error.code && <code>{error.code}</code>}{error.requestId && <small>{t("requestId")}: {error.requestId}</small>}</div>
          <button className="icon-button" type="button" onClick={() => setError(null)} aria-label={t("close")}><X size={17} /></button>
        </div>
      )}
    </div>
  );
}

function SettingsForm({
  operation,
  fields,
  updateField,
  t
}: {
  operation: Operation;
  fields: Record<string, string | number | boolean>;
  updateField: (name: string, value: string | number | boolean) => void;
  t: (key: MessageKey) => string;
}) {
  if (operation === "identify") return <div className="identify-note"><Check size={18} /><span>{t("identifyDescription")}</span></div>;

  const select = (name: string, label: MessageKey, options: Array<[string, MessageKey]>) => (
    <label className="field">
      <span>{t(label)}</span>
      <select value={String(fields[name])} onChange={(event) => updateField(name, event.target.value)}>
        {options.map(([value, key]) => <option value={value} key={value}>{t(key)}</option>)}
      </select>
    </label>
  );

  const toggle = (name: string, label: MessageKey) => (
    <label className="toggle-field">
      <input type="checkbox" checked={Boolean(fields[name])} onChange={(event) => updateField(name, event.target.checked)} />
      <i><span /></i>
      <span>{t(label)}</span>
    </label>
  );

  return (
    <div className="settings-form">
      {(operation === "visible" || operation === "all") && (
        <div className="field-grid">
          {select("sensitivity", "sensitivity", [["auto", "sensitivityAuto"], ["strict", "sensitivityStrict"], ["assume_ai", "sensitivityAssume"]])}
          {select("backend", "backend", [["cv2", "backendCv2"], ["migan", "backendMigan"], ["lama", "backendLama"]])}
        </div>
      )}
      {operation === "visible" && toggle("strip_metadata", "stripMetadata")}
      {operation === "metadata" && toggle("keep_standard", "keepStandard")}
      {operation === "erase" && (
        <>
          <div className="field-grid">
            {select("backend", "backend", [["cv2", "backendCv2"], ["migan", "backendMigan"], ["lama", "backendLama"]])}
            {select("method", "method", [["telea", "methodTelea"], ["ns", "methodNs"]])}
            <NumberField name="dilate" label="dilate" min={0} max={100} value={fields.dilate} updateField={updateField} t={t} />
          </div>
          {toggle("strip_metadata", "stripMetadata")}
        </>
      )}
      {(operation === "invisible" || operation === "all") && (
        <>
          <div className="field-grid">
            <label className="field"><span>{t("pipeline")}</span><select value={String(fields.pipeline)} onChange={(event) => updateField("pipeline", event.target.value)}><option value="controlnet">ControlNet</option><option value="sdxl">SDXL</option><option value="qwen">Qwen</option></select></label>
            <NumberField name="strength" label="strength" min={0} max={1} step={0.05} placeholder={t("adaptive")} value={fields.strength} updateField={updateField} t={t} />
            <NumberField name="steps" label="steps" min={1} max={200} value={fields.steps} updateField={updateField} t={t} />
            <NumberField name="seed" label="seed" placeholder={t("optional")} value={fields.seed} updateField={updateField} t={t} />
          </div>
          {toggle("force", "force")}
          <details className="advanced-panel">
            <summary>{t("advancedSettings")}</summary>
            <div className="field-grid">
              <NumberField name="max_resolution" label="maxResolution" min={0} max={8192} value={fields.max_resolution} updateField={updateField} t={t} />
              <NumberField name="min_resolution" label="minResolution" min={0} max={4096} value={fields.min_resolution} updateField={updateField} t={t} />
              <NumberField name="tile_size" label="tileSize" min={512} max={2048} value={fields.tile_size} updateField={updateField} t={t} />
              <NumberField name="tile_overlap" label="tileOverlap" min={0} max={512} value={fields.tile_overlap} updateField={updateField} t={t} />
            </div>
            {toggle("tile", "tile")}
          </details>
        </>
      )}
    </div>
  );
}

function NumberField({
  name,
  label,
  value,
  min,
  max,
  step,
  placeholder,
  updateField,
  t
}: {
  name: string;
  label: MessageKey;
  value: string | number | boolean;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  updateField: (name: string, value: string | number | boolean) => void;
  t: (key: MessageKey) => string;
}) {
  return (
    <label className="field">
      <span>{t(label)}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={String(value)}
        placeholder={placeholder}
        onChange={(event) => updateField(name, event.target.value === "" ? "" : Number(event.target.value))}
      />
    </label>
  );
}
