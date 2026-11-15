import type { ConsentChannel, ConsentMethod, ContactMethod, FuelType, Transmission } from "./api/types";

export const CONTACT_METHOD: Record<ContactMethod, string> = {
  phone: "Phone call",
  whatsapp: "WhatsApp",
  email: "Email",
  sms: "SMS",
};

export const CONSENT_CHANNEL: Record<ConsentChannel, string> = {
  whatsapp: "WhatsApp messages",
  sms: "SMS messages",
  email: "Email",
  marketing: "Marketing and service reminders",
};

export const CONSENT_METHOD: Record<ConsentMethod, string> = {
  verbal: "Verbal",
  written: "Written",
  signed_form: "Signed form",
  customer_portal: "Customer portal",
  other: "Other",
};

export const FUEL_TYPE: Record<FuelType, string> = {
  petrol: "Petrol",
  diesel: "Diesel",
  hybrid: "Hybrid",
  electric: "Electric",
  lpg: "LPG",
  other: "Other",
};

export const TRANSMISSION: Record<Transmission, string> = {
  manual: "Manual",
  automatic: "Automatic",
  other: "Other",
};

export function vehicleTitle(v: { registration_number: string | null; vin: string | null }): string {
  return v.registration_number ?? v.vin ?? "Unregistered";
}

export function formatKm(km: number | null): string {
  return km == null ? "—" : `${km.toLocaleString("en-ZA").replace(/,/g, " ")} km`;
}

/** Display a stored phone number in readable groups: 081 234 5678, +264 81 234 5678. */
export function formatPhone(value: string | null): string {
  if (!value) return "—";
  const m264 = /^\+264(\d{2})(\d{3})(\d{3,4})$/.exec(value);
  if (m264) return `+264 ${m264[1]} ${m264[2]} ${m264[3]}`;
  const local = /^(0\d{2})(\d{3})(\d{3,4})$/.exec(value);
  if (local) return `${local[1]} ${local[2]} ${local[3]}`;
  return value;
}
