import { Archive, Cpu, RefreshCw, Server } from "lucide-react";
import type { ReactNode } from "react";
import type { MessageKey } from "../i18n";
import type { Capabilities } from "../types";

interface SystemStatusProps {
  capabilities: Capabilities | null;
  ready: boolean;
  loading: boolean;
  onRefresh: () => void;
  t: (key: MessageKey) => string;
}

export function SystemStatus({ capabilities, ready, loading, onRefresh, t }: SystemStatusProps) {
  return (
    <section className="status-panel" aria-labelledby="status-heading">
      <div className="section-heading inline-heading">
        <div>
          <span className="eyebrow">{t("systemStatus")}</span>
          <h2 id="status-heading">{ready ? t("online") : t("offline")}</h2>
        </div>
        <button className="icon-button" type="button" onClick={onRefresh} aria-label={t("refresh")}>
          <RefreshCw size={17} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="status-grid">
        <StatusItem icon={<Server size={18} />} label={t("apiService")} active={ready} value={capabilities?.app_version} />
        <StatusItem
          icon={<Archive size={18} />}
          label={t("archiveService")}
          active={Boolean(capabilities?.archive_ready)}
          value={capabilities?.archive_ready ? t("available") : t("unavailable")}
        />
        <StatusItem
          icon={<Cpu size={18} />}
          label={t("gpuQueue")}
          active={Boolean(capabilities?.redis_ready)}
          value={capabilities?.redis_ready ? t("available") : t("unavailable")}
        />
      </div>
      {capabilities && (
        <div className="status-meta">
          <span>{t("upstream")} {capabilities.upstream_version}</span>
          <span>{t("limits")} {capabilities.max_upload_mb} MB</span>
          <span>{capabilities.supported_formats.map((format) => format.toUpperCase()).join(" · ")}</span>
        </div>
      )}
    </section>
  );
}

function StatusItem({ icon, label, active, value }: { icon: ReactNode; label: string; active: boolean; value?: string }) {
  return (
    <div className="status-item">
      <div className={`status-icon ${active ? "active" : ""}`}>{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value ?? "—"}</strong>
      </div>
      <i className={`status-dot ${active ? "active" : ""}`} aria-hidden="true" />
    </div>
  );
}
