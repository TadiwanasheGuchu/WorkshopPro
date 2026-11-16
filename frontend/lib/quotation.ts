import type { StatusTone } from "@/components/status-badge";

import type { LineKind, QuoteStatus } from "./api/types";

export const QUOTE_STATUS: Record<QuoteStatus, { tone: StatusTone; label: string }> = {
  draft: { tone: "neutral", label: "Draft" },
  sent: { tone: "active", label: "Sent" },
  approved: { tone: "success", label: "Approved" },
  rejected: { tone: "danger", label: "Rejected" },
  expired: { tone: "danger", label: "Expired" },
  superseded: { tone: "neutral", label: "Superseded" },
  withdrawn: { tone: "neutral", label: "Withdrawn" },
};

export const LINE_KIND: Record<LineKind, string> = { labour: "Labour", part: "Part", fee: "Fee", discount: "Discount" };

export const DECISION_METHOD: Record<string, string> = {
  customer_link: "Online, through the quotation link",
  in_person: "In person",
  phone: "By phone",
  email: "By email",
  whatsapp: "By WhatsApp",
  other: "Other",
};
