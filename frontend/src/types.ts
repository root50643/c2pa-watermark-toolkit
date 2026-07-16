import type { components } from "./generated/api";

export type Capabilities = components["schemas"]["CapabilitiesResponse"];
export type Customer = components["schemas"]["MeResponse"];
export type IdentifyResult = components["schemas"]["IdentifyResponse"];
export type JobAccepted = components["schemas"]["JobAccepted"];
export type JobStatus = components["schemas"]["JobStatus"];

export type Locale = "zh-TW" | "en";
export type Operation = "identify" | "visible" | "erase" | "metadata" | "invisible" | "all";

export interface Region {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ImageDimensions {
  width: number;
  height: number;
}

export interface BinaryResult {
  blob: Blob;
  filename: string;
  requestId: string | null;
  archiveId: string | null;
  removedMarks: string | null;
}

export interface TrackedJob {
  jobId: string;
  archiveId: string;
  taskName: "invisible" | "all";
  createdAt: string;
  status?: JobStatus;
  pollingError?: string;
}
