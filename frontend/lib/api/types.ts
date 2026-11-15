/**
 * API response types. Mirrors backend/app/schemas. Keep in sync when schemas change
 * (OpenAPI type generation is planned once the API surface stabilises).
 */

export type UUID = string;

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
  request_id?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface BranchSummary {
  id: UUID;
  name: string;
  code: string;
}

export interface Me {
  id: UUID;
  email: string;
  full_name: string;
  is_owner: boolean;
  organisation: {
    id: UUID;
    name: string;
    currency_code: string;
    timezone: string;
    date_format: DateFormat;
  };
  permissions: string[];
  branch_permissions: Record<UUID, string[]>;
  branches: BranchSummary[];
}

export type DateFormat = "DD/MM/YYYY" | "YYYY-MM-DD" | "MM/DD/YYYY";

export interface Organisation {
  id: UUID;
  name: string;
  legal_name: string | null;
  registration_number: string | null;
  tax_number: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  postal_code: string | null;
  country_code: string;
}

export interface OrganisationSettings {
  currency_code: string;
  timezone: string;
  date_format: DateFormat;
  prices_include_tax: boolean;
  document_footer: string | null;
}

export interface TaxRate {
  id: UUID;
  name: string;
  rate_percent: string;
  description: string | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface DocumentSequence {
  document_type: string;
  label: string;
  prefix: string;
  next_number: number;
  padding: number;
  example: string;
  last_allocated_at: string | null;
}

export interface Branch {
  id: UUID;
  name: string;
  code: string;
  email: string | null;
  phone: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  postal_code: string | null;
  archived_at: string | null;
  created_at: string;
}

export interface OperatingHours {
  weekday: number;
  is_closed: boolean;
  opens_at: string | null;
  closes_at: string | null;
}

export interface BranchDetail extends Branch {
  operating_hours: OperatingHours[];
}

export interface ServiceBay {
  id: UUID;
  branch_id: UUID;
  name: string;
  description: string | null;
  is_active: boolean;
}

export type UserStatus = "active" | "invited" | "deactivated";

export interface RoleAssignment {
  id: UUID;
  role_id: UUID;
  role_name: string;
  branch_id: UUID | null;
  branch_name: string | null;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  phone: string | null;
  status: UserStatus;
  is_owner: boolean;
  last_login_at: string | null;
  invited_at: string | null;
  activated_at: string | null;
  created_at: string;
  role_assignments: RoleAssignment[];
}

export interface Permission {
  code: string;
  module: string;
  label: string;
  description: string;
  scope: "organisation" | "branch";
}

export interface Role {
  id: UUID;
  name: string;
  description: string | null;
  is_owner: boolean;
  template_key: string | null;
  archived_at: string | null;
  permissions: string[];
  user_count: number;
}

export interface AuditLogEntry {
  id: UUID;
  created_at: string;
  action: string;
  entity_type: string;
  entity_id: UUID | null;
  summary: string;
  changes: Record<string, unknown> | null;
  actor_type: string;
  actor_user_id: UUID | null;
  actor_name: string | null;
  branch_id: UUID | null;
  branch_name: string | null;
  ip_address: string | null;
  request_id: string | null;
}

export interface TokenInfo {
  purpose: "invitation" | "password_reset";
  email: string;
  full_name: string;
  organisation_name: string;
}

export interface Readiness {
  status: "ok" | "error";
  checks: Record<string, { status: "ok" | "error"; latency_ms?: number | null }>;
}

// --------------------------------------------------------------------------- customers & vehicles

export type CustomerType = "individual" | "company";
export type ContactMethod = "phone" | "whatsapp" | "email" | "sms";
export type ConsentChannel = "whatsapp" | "sms" | "email" | "marketing";
export type ConsentMethod = "verbal" | "written" | "signed_form" | "customer_portal" | "other";

export interface CustomerSummary {
  id: UUID;
  customer_type: CustomerType;
  display_name: string;
  primary_phone: string | null;
  primary_email: string | null;
  vehicle_count: number;
  archived_at: string | null;
  created_at: string;
}

export interface CustomerContact {
  id: UUID;
  kind: "phone" | "email";
  label: string | null;
  value: string;
  is_primary: boolean;
}

export interface CustomerAddress {
  id: UUID;
  kind: "physical" | "postal";
  line1: string;
  line2: string | null;
  city: string | null;
  region: string | null;
  postal_code: string | null;
}

export interface Consent {
  id: UUID;
  channel: ConsentChannel;
  status: "granted" | "withdrawn";
  method: ConsentMethod;
  evidence: string | null;
  recorded_at: string;
  recorded_by: string | null;
}

export interface VehicleBrief {
  id: UUID;
  registration_number: string | null;
  vin: string | null;
  make: string;
  model: string;
  year: number | null;
  archived_at: string | null;
}

export interface CustomerDetail {
  id: UUID;
  customer_type: CustomerType;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  contact_person: string | null;
  registration_number: string | null;
  tax_number: string | null;
  preferred_contact_method: ContactMethod;
  notes: string | null;
  archived_at: string | null;
  created_at: string;
  contacts: CustomerContact[];
  addresses: CustomerAddress[];
  consents: Consent[];
  vehicles: VehicleBrief[];
}

export type FuelType = "petrol" | "diesel" | "hybrid" | "electric" | "lpg" | "other";
export type Transmission = "manual" | "automatic" | "other";

export interface Vehicle {
  id: UUID;
  customer: { id: UUID; display_name: string };
  registration_number: string | null;
  vin: string | null;
  engine_number: string | null;
  make: string;
  model: string;
  variant: string | null;
  year: number | null;
  fuel_type: FuelType | null;
  transmission: Transmission | null;
  colour: string | null;
  odometer_km: number | null;
  odometer_recorded_at: string | null;
  existing_damage: string | null;
  notes: string | null;
  archived_at: string | null;
  created_at: string;
}

export interface Ownership {
  customer: { id: UUID; display_name: string };
  started_at: string;
  ended_at: string | null;
  note: string | null;
}
