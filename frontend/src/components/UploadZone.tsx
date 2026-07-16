import { FileImage, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import type { MessageKey } from "../i18n";

interface UploadZoneProps {
  file: File | null;
  maxMb: number;
  onFile: (file: File) => void;
  t: (key: MessageKey) => string;
}

export function UploadZone({ file, maxMb, onFile, t }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const receive = (files: FileList | null) => {
    const next = files?.[0];
    if (next) onFile(next);
  };

  return (
    <div
      className={`upload-zone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        receive(event.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept=".png,.jpg,.jpeg,.webp,.heic,.heif,.avif,image/png,image/jpeg,image/webp,image/heic,image/heif,image/avif"
        onChange={(event) => receive(event.currentTarget.files)}
      />
      <div className="upload-icon" aria-hidden="true">
        {file ? <FileImage size={27} /> : <UploadCloud size={27} />}
      </div>
      <div className="upload-copy">
        <strong>{file ? file.name : t("uploadTitle")}</strong>
        <span>
          {file
            ? `${(file.size / 1024 / 1024).toFixed(2)} MB · ${t("limits")} ${maxMb} MB`
            : t("uploadDescription")}
        </span>
      </div>
      <button className="button secondary compact" type="button" onClick={() => inputRef.current?.click()}>
        {file ? t("replaceFile") : t("chooseFile")}
      </button>
    </div>
  );
}
