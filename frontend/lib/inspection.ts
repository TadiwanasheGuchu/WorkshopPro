import type { StatusTone } from "@/components/status-badge";

import type { InspectionKind, InspectionResult } from "./api/types";

/** Status families from CLAUDE.md §9: Pass green, Attention yellow, Failed red, Not inspected neutral. */
export const RESULT_TONE: Record<InspectionResult, StatusTone> = {
  pass: "success",
  attention: "waiting",
  fail: "danger",
  not_inspected: "neutral",
};

export const RESULT_LABEL: Record<InspectionResult, string> = {
  pass: "Pass",
  attention: "Attention required",
  fail: "Failed",
  not_inspected: "Not inspected",
};

export const RESULT_SHORT: Record<InspectionResult, string> = {
  pass: "Pass",
  attention: "Attention",
  fail: "Fail",
  not_inspected: "N/A",
};

export const KIND_LABEL: Record<InspectionKind, string> = {
  intake: "Intake inspection",
  quality: "Quality inspection",
  other: "Inspection",
};

/** Downscale a camera photo in the browser before upload (slow connections). */
export async function compressPhoto(file: File, maxEdge = 1920, quality = 0.85): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    // Unsupported format in this browser (e.g. HEIC on desktop): upload as-is; the server validates.
    return file;
  }
}
