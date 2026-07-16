import { Download, FileSearch, Image as ImageIcon } from "lucide-react";
import type { MessageKey } from "../i18n";
import type { BinaryResult, IdentifyResult } from "../types";

interface ResultPanelProps {
  sourceUrl: string | null;
  resultUrl: string | null;
  binary: BinaryResult | null;
  report: IdentifyResult | null;
  onDownload: () => void;
  t: (key: MessageKey) => string;
}

export function ResultPanel({ sourceUrl, resultUrl, binary, report, onDownload, t }: ResultPanelProps) {
  return (
    <section className="result-panel" aria-labelledby="result-heading">
      <div className="section-heading">
        <span className="eyebrow">OUTPUT</span>
        <h2 id="result-heading">{t("result")}</h2>
      </div>
      {!binary && !report ? (
        <div className="empty-result">
          <div><ImageIcon size={25} /></div>
          <p>{t("noResult")}</p>
        </div>
      ) : report ? (
        <div className="report-card">
          <div className="report-title"><FileSearch size={19} /><strong>{t("identifyReport")}</strong></div>
          <pre>{JSON.stringify(report.report, null, 2)}</pre>
          <div className="request-meta">
            <span>{t("requestId")} <code>{report.request_id}</code></span>
            <span>{t("archiveId")} <code>{report.archive_id}</code></span>
          </div>
        </div>
      ) : (
        <div>
          <div className="comparison-grid">
            <figure>
              <figcaption>{t("original")}</figcaption>
              {sourceUrl && <img src={sourceUrl} alt={t("original")} />}
            </figure>
            <figure>
              <figcaption>{t("processed")}</figcaption>
              {resultUrl && <img src={resultUrl} alt={t("processed")} />}
            </figure>
          </div>
          <div className="result-actions">
            <div className="request-meta">
              {binary?.requestId && <span>{t("requestId")} <code>{binary.requestId}</code></span>}
              {binary?.archiveId && <span>{t("archiveId")} <code>{binary.archiveId}</code></span>}
              {binary?.removedMarks && <span>{t("removedMarks")} <code>{binary.removedMarks}</code></span>}
            </div>
            <button className="button primary" type="button" onClick={onDownload}>
              <Download size={17} /> {t("download")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
