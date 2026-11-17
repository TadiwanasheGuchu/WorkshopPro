import type { StatusTone } from "@/components/status-badge";

import type { NotificationStatus } from "./api/types";

export const NOTIFICATION_STATUS: Record<NotificationStatus, { tone: StatusTone; label: string }> = {
  queued: { tone: "waiting", label: "Sending" },
  sent: { tone: "active", label: "Sent" },
  delivered: { tone: "success", label: "Delivered" },
  read: { tone: "success", label: "Read" },
  failed: { tone: "danger", label: "Failed" },
  skipped: { tone: "neutral", label: "Not sent" },
};

export const CHANNEL_LABEL = { email: "Email", whatsapp: "WhatsApp", none: "—" } as const;
