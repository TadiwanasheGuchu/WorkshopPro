import type { StatusTone } from "@/components/status-badge";

import type { ExceptionType, FuelLevel, JobStatus, Priority } from "./api/types";

/** Status colour families from CLAUDE.md §9. */
export const JOB_STATUS_TONE: Record<JobStatus, StatusTone> = {
  vehicle_received: "neutral",
  inspection_pending: "neutral",
  diagnosis_in_progress: "active",
  awaiting_approval: "waiting",
  awaiting_parts: "waiting",
  repair_in_progress: "active",
  quality_inspection: "active",
  ready_for_collection: "success",
  completed: "neutral",
  cancelled: "neutral",
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  vehicle_received: "Vehicle received",
  inspection_pending: "Inspection pending",
  diagnosis_in_progress: "Diagnosis in progress",
  awaiting_approval: "Awaiting quotation approval",
  awaiting_parts: "Awaiting parts",
  repair_in_progress: "Repair in progress",
  quality_inspection: "Quality inspection",
  ready_for_collection: "Ready for collection",
  completed: "Completed / collected",
  cancelled: "Cancelled",
};

export const PRIORITY_LABEL: Record<Priority, string> = { low: "Low", normal: "Normal", high: "High", urgent: "Urgent" };

export const FUEL_LEVEL_LABEL: Record<FuelLevel, string> = {
  empty: "Empty",
  quarter: "¼",
  half: "½",
  three_quarters: "¾",
  full: "Full",
};

export const EXCEPTION_TYPE_LABEL: Record<ExceptionType, string> = {
  customer_verbal: "Customer approved verbally",
  customer_written: "Customer approved in writing (no quotation)",
  warranty: "Warranty work",
  internal_no_charge: "Internal / no charge",
  safety_emergency: "Safety emergency",
  other: "Other",
};

/** Verb-style labels for action buttons. */
export const TRANSITION_ACTION: Record<JobStatus, string> = {
  vehicle_received: "Mark received",
  inspection_pending: "Send for inspection",
  diagnosis_in_progress: "Start diagnosis",
  awaiting_approval: "Send for customer approval",
  awaiting_parts: "Waiting for parts",
  repair_in_progress: "Start repair",
  quality_inspection: "Send to quality check",
  ready_for_collection: "Ready for collection",
  completed: "Hand over vehicle",
  cancelled: "Cancel job",
};
