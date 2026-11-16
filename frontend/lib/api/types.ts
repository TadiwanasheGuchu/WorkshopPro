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
  quotation_validity_days: number;
  quotation_terms: string | null;
  invoice_payment_days: number;
  invoice_terms: string | null;
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

// --------------------------------------------------------------------------- job cards

export type JobStatus =
  | "vehicle_received"
  | "inspection_pending"
  | "diagnosis_in_progress"
  | "awaiting_approval"
  | "awaiting_parts"
  | "repair_in_progress"
  | "quality_inspection"
  | "ready_for_collection"
  | "completed"
  | "cancelled";
export type Priority = "low" | "normal" | "high" | "urgent";
export type FuelLevel = "empty" | "quarter" | "half" | "three_quarters" | "full";
export type ExceptionType =
  | "customer_verbal"
  | "customer_written"
  | "warranty"
  | "internal_no_charge"
  | "safety_emergency"
  | "other";

export interface Ref {
  id: UUID;
  name: string;
}

export interface JobCardSummary {
  id: UUID;
  job_number: string;
  status: JobStatus;
  status_label: string;
  priority: Priority;
  branch: Ref;
  customer: Ref;
  vehicle: { id: UUID; registration_number: string | null; vin: string | null; make: string; model: string; year: number | null };
  complaint: string;
  received_at: string;
  promised_at: string | null;
  is_overdue: boolean;
  assignees: Ref[];
}

export interface TransitionOption {
  to_status: JobStatus;
  label: string;
  allowed: boolean;
  reason: string | null;
}

export interface JobCardDetail extends JobCardSummary {
  requested_work: string | null;
  diagnosis: string | null;
  work_performed: string | null;
  intake_odometer_km: number | null;
  fuel_level: FuelLevel | null;
  service_bay: Ref | null;
  received_by: string | null;
  collected_at: string | null;
  collected_by_name: string | null;
  handover_notes: string | null;
  cancellation_reason: string | null;
  version: number;
  approval_status: "not_required_yet" | "quotation_approved" | "exception_active" | "missing";
  assignments: { user: Ref; assigned_at: string; assigned_by: string | null; unassigned_at: string | null }[];
  status_history: { from_status: JobStatus | null; to_status: JobStatus; note: string | null; changed_at: string; changed_by: string | null }[];
  notes: { id: UUID; body: string; visibility: "internal" | "customer"; author: string | null; created_at: string }[];
  inspections: InspectionSummary[];
  approval_exceptions: {
    id: UUID;
    exception_type: ExceptionType;
    reason: string;
    scope: string;
    customer_contact: string | null;
    max_amount: string | null;
    currency_code: string;
    authorised_by: string;
    authorised_at: string;
    revoked_at: string | null;
    revoked_by: string | null;
    revoke_reason: string | null;
  }[];
  capabilities: {
    edit_details: boolean;
    edit_work: boolean;
    assign: boolean;
    add_notes: boolean;
    authorise_exception: boolean;
    transitions: TransitionOption[];
  };
}

export interface AssignableUser {
  id: UUID;
  full_name: string;
  active_jobs: number;
}

export interface JobSummaryCounts {
  by_status: Record<JobStatus, number>;
  open_total: number;
  overdue: number;
  received_today: number;
  my_assigned_open: number;
}

// --------------------------------------------------------------------------- inspections

export type InspectionResult = "pass" | "attention" | "fail" | "not_inspected";
export type InspectionKind = "intake" | "quality" | "other";

export interface InspectionSummary {
  id: UUID;
  kind: InspectionKind;
  status: "draft" | "submitted";
  template_name: string;
  started_by: string | null;
  submitted_at: string | null;
  counts: Record<InspectionResult, number>;
}

export interface InspectionPhoto {
  id: UUID;
  file_id: UUID;
  item_id: UUID | null;
  caption: string | null;
  created_at: string;
}

export interface InspectionItem {
  id: UUID;
  section: string;
  label: string;
  guidance: string | null;
  result: InspectionResult;
  notes: string | null;
  photos: InspectionPhoto[];
}

export interface InspectionDetail extends InspectionSummary {
  job_card: { id: UUID; job_number: string };
  vehicle: { id: UUID; registration_number: string | null; vin: string | null; make: string; model: string; year: number | null };
  customer_name: string;
  branch_name: string;
  organisation_name: string;
  odometer_km: number | null;
  summary: string | null;
  submitted_by: string | null;
  created_at: string;
  items: InspectionItem[];
  general_photos: InspectionPhoto[];
  amendments: {
    item_label: string;
    old_result: InspectionResult;
    new_result: InspectionResult;
    old_notes: string | null;
    new_notes: string | null;
    reason: string;
    amended_by: string;
    amended_at: string;
  }[];
  capabilities: { edit: boolean; amend: boolean };
}

export interface InspectionTemplate {
  id: UUID;
  name: string;
  description: string | null;
  is_default: boolean;
  archived_at: string | null;
  item_count: number;
  items: { id: UUID; section: string; label: string; guidance: string | null }[] | null;
}

// --------------------------------------------------------------------------- appointments

export type AppointmentStatus = "booked" | "arrived" | "cancelled" | "no_show";

export interface Appointment {
  id: UUID;
  branch: Ref;
  customer: Ref;
  vehicle: JobCardSummary["vehicle"] | null;
  service_bay: Ref | null;
  assigned_user: Ref | null;
  starts_at: string;
  ends_at: string;
  local_date: string;
  local_start: string;
  local_end: string;
  duration_minutes: number;
  reason: string;
  notes: string | null;
  status: AppointmentStatus;
  cancellation_reason: string | null;
  job_card: Ref | null;
  created_by: string | null;
}

export interface DaySchedule {
  date: string;
  timezone: string;
  opens_at: string | null;
  closes_at: string | null;
  is_closed: boolean;
  bays: Ref[];
  appointments: Appointment[];
}

// --------------------------------------------------------------------------- quotations

export type QuoteStatus = "draft" | "sent" | "approved" | "rejected" | "superseded" | "withdrawn" | "expired";
export type LineKind = "labour" | "part" | "fee" | "discount";

export interface QuoteItem {
  id: UUID;
  kind: LineKind;
  description: string;
  part_number: string | null;
  quantity: string;
  unit_price: string;
  tax_rate_id: UUID | null;
  tax_rate_name: string | null;
  tax_rate_percent: string;
  line_subtotal: string;
  line_tax: string;
  line_total: string;
}

export interface QuoteVersion {
  id: UUID;
  version_number: number;
  status: QuoteStatus;
  currency_code: string;
  prices_include_tax: boolean;
  valid_until: string | null;
  terms: string | null;
  notes: string | null;
  subtotal: string;
  tax_total: string;
  total: string;
  sent_at: string | null;
  sent_by: string | null;
  created_at: string;
  revision_reason: string | null;
  items: QuoteItem[];
  decision: {
    decision: "approved" | "rejected";
    method: string;
    total: string;
    currency_code: string;
    customer_name: string;
    evidence: string | null;
    comments: string | null;
    recorded_by: string | null;
    decided_at: string;
  } | null;
  link: { expires_at: string; first_viewed_at: string | null; last_viewed_at: string | null; view_count: number; used_at: string | null; revoked_at: string | null } | null;
}

export interface Quotation {
  id: UUID;
  quote_number: string;
  branch: Ref;
  job_card: Ref;
  customer: Ref;
  customer_email: string | null;
  vehicle: JobCardSummary["vehicle"];
  current: QuoteVersion;
  versions: { id: UUID; version_number: number; status: QuoteStatus; total: string; sent_at: string | null }[];
  capabilities: { edit: boolean; send: boolean; revise: boolean; record_decision: boolean };
}

export interface QuotationListItem {
  id: UUID;
  quote_number: string;
  version_number: number;
  status: QuoteStatus;
  total: string;
  currency_code: string;
  customer: Ref;
  vehicle: JobCardSummary["vehicle"];
  job_card: Ref;
  updated_at: string;
}

export interface PublicQuotation {
  organisation_name: string;
  organisation_phone: string | null;
  organisation_email: string | null;
  branch_name: string;
  quote_number: string;
  version_number: number;
  status: QuoteStatus;
  customer_name: string;
  vehicle: string;
  currency_code: string;
  prices_include_tax: boolean;
  items: { kind: LineKind; description: string; quantity: string; unit_price: string; tax_rate_percent: string; line_total: string }[];
  subtotal: string;
  tax_total: string;
  total: string;
  valid_until: string | null;
  terms: string | null;
  notes: string | null;
  can_decide: boolean;
  decision: "approved" | "rejected" | null;
  decided_at: string | null;
}

// --------------------------------------------------------------------------- invoices

export type PaymentMethod = "cash" | "eft" | "card" | "mobile" | "cheque" | "other";
export type InvoicePaymentStatus = "draft" | "unpaid" | "partially_paid" | "paid" | "credited" | "overpaid";
export type PaymentKind = "payment" | "refund" | "reversal";

export interface InvoiceListItem {
  id: UUID;
  invoice_number: string | null;
  status: "draft" | "issued";
  payment_status: InvoicePaymentStatus;
  customer: Ref;
  job_card: Ref | null;
  issue_date: string | null;
  due_date: string | null;
  is_overdue: boolean;
  currency_code: string;
  total: string;
  balance_due: string;
}

export interface CreditNote {
  id: UUID;
  credit_note_number: string;
  issue_date: string;
  reason: string;
  subtotal: string;
  tax_total: string;
  total: string;
  created_by: string;
}

export interface InvoicePaymentLine {
  payment_id: UUID;
  receipt_number: string;
  kind: PaymentKind;
  method: PaymentMethod;
  received_at: string;
  amount: string;
}

export interface Invoice extends InvoiceListItem {
  branch: Ref;
  prices_include_tax: boolean;
  items: QuoteItem[];
  subtotal: string;
  tax_total: string;
  amount_paid: string;
  amount_credited: string;
  notes: string | null;
  terms: string | null;
  issued_at: string | null;
  issued_by: string | null;
  quotation_version_id: UUID | null;
  credit_notes: CreditNote[];
  payments: InvoicePaymentLine[];
  capabilities: { edit: boolean; issue: boolean; delete: boolean; credit: boolean; record_payment: boolean; refund: boolean };
}

export interface Payment {
  id: UUID;
  receipt_number: string;
  kind: PaymentKind;
  method: PaymentMethod;
  amount: string;
  currency_code: string;
  received_at: string;
  reference: string | null;
  notes: string | null;
  branch: Ref;
  customer: Ref;
  recorded_by: string;
  allocations: { invoice_id: UUID; invoice_number: string | null; amount: string }[];
  unallocated: string;
  reversed_by_receipt: string | null;
  reverses_receipt: string | null;
}

export interface CustomerBalance {
  customer_id: UUID;
  currency_code: string;
  outstanding: string;
  unallocated_credit: string;
  open_invoices: InvoiceListItem[];
}

// --------------------------------------------------------------------------- reports

export interface ReportPeriod {
  date_from: string;
  date_to: string;
  timezone: string;
}

export interface CountAmount {
  count: number;
  total: string;
}

export interface FinancialReport {
  period: ReportPeriod;
  branch: Ref | null;
  currency_code: string;
  invoiced: { count: number; subtotal: string; tax_total: string; total: string };
  credited: CountAmount;
  net_invoiced: string;
  received: CountAmount;
  refunded: CountAmount;
  reversed: CountAmount;
  net_received: string;
  by_method: { method: PaymentMethod; received: string; paid_out: string }[];
  daily: { date: string; invoiced: string; received: string }[];
  receivables: {
    as_at: string;
    outstanding: string;
    overdue: string;
    open_invoices: number;
    ageing: { bucket: string; count: number; amount: string }[];
    unapplied_credit: string;
  };
  definitions: { term: string; definition: string }[];
}

export interface OperationsReport {
  period: ReportPeriod;
  branch: Ref | null;
  currency_code: string;
  received: number;
  completed: number;
  cancelled: number;
  turnaround_hours_avg: number | null;
  turnaround_hours_median: number | null;
  open_by_status: Partial<Record<JobStatus, number>>;
  open_total: number;
  overdue_now: number;
  quotations: { sent: number; approved: number; rejected: number; approved_value: string };
  mechanics: { user_id: UUID; name: string; open_jobs: number; completed_in_period: number }[];
  definitions: { term: string; definition: string }[];
}

// --------------------------------------------------------------------------- inventory

export type PartUnit = "each" | "pair" | "set" | "box" | "litre" | "kg" | "metre";
export type MovementKind = "opening" | "adjustment" | "transfer_out" | "transfer_in" | "receipt" | "issue" | "return" | "supplier_return";

export interface PartCategory {
  id: UUID;
  name: string;
  archived_at: string | null;
  part_count: number;
}

export interface StockSummary {
  on_hand: string;
  reserved: string;
  available: string;
  low_locations: number;
}

export interface PartListItem {
  id: UUID;
  sku: string;
  name: string;
  category: Ref | null;
  unit: PartUnit;
  manufacturer_part_number: string | null;
  selling_price: string;
  cost_price: string | null;
  archived_at: string | null;
  stock: StockSummary;
}

export interface StockLevelRow {
  location: Ref;
  branch: Ref;
  on_hand: string;
  reserved: string;
  available: string;
  min_quantity: string | null;
  is_low: boolean;
  can_adjust: boolean;
  can_transfer: boolean;
}

export interface Part extends PartListItem {
  description: string | null;
  manufacturer: string | null;
  tax_rate: Ref | null;
  created_at: string;
  updated_at: string;
  levels: StockLevelRow[];
  capabilities: { edit: boolean; archive: boolean };
}

export interface StockLocation {
  id: UUID;
  name: string;
  branch: Ref;
  is_default: boolean;
  archived_at: string | null;
  part_count: number;
  units_on_hand: string;
}

export interface StockMovement {
  id: UUID;
  operation_id: UUID;
  kind: MovementKind;
  part: Ref;
  sku: string;
  location: Ref;
  branch: Ref;
  quantity: string;
  balance_after: string | null;
  unit_cost: string | null;
  job_card: Ref | null;
  reason: string | null;
  reference: string | null;
  created_by: string;
  created_at: string;
}

export interface StockOperation {
  id: UUID;
  kind: string;
  reason: string | null;
  created_at: string;
  movements: StockMovement[];
  unchanged_part_ids: UUID[];
}

export interface JobPartReservation {
  id: UUID;
  part: Ref;
  sku: string;
  unit: PartUnit;
  location: Ref;
  quantity: string;
  issued_quantity: string;
  released_quantity: string;
  outstanding: string;
  status: "open" | "closed";
  release_reason: string | null;
  created_by: string;
  created_at: string;
}

export interface JobParts {
  job_card_id: UUID;
  authorised: boolean;
  currency_code: string;
  capabilities: { reserve: boolean; issue: boolean; return_parts: boolean; release: boolean };
  locations: Ref[];
  reservations: JobPartReservation[];
  used: { part: Ref; sku: string; unit: PartUnit; issued: string; selling_price: string; value: string }[];
  movements: StockMovement[];
}

// --------------------------------------------------------------------------- purchasing

export type PoStatus = "draft" | "approved" | "partially_received" | "received" | "closed" | "cancelled";

export interface SupplierListItem {
  id: UUID;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  archived_at: string | null;
  open_orders: number;
}

export interface Supplier extends SupplierListItem {
  address: string | null;
  tax_number: string | null;
  account_number: string | null;
  payment_terms_days: number;
  notes: string | null;
  parts: { part: Ref; sku: string; unit: PartUnit; supplier_sku: string | null; last_cost: string | null; lead_time_days: number | null }[];
  received_value_90_days: string;
  capabilities: { edit: boolean; archive: boolean };
}

export interface PoListItem {
  id: UUID;
  po_number: string;
  status: PoStatus;
  supplier: Ref;
  branch: Ref;
  expected_date: string | null;
  is_overdue: boolean;
  total: string;
  currency_code: string;
  created_at: string;
}

export interface PoLine {
  id: UUID;
  part: Ref;
  sku: string;
  unit: PartUnit;
  supplier_sku: string | null;
  quantity_ordered: string;
  quantity_received: string;
  quantity_returned: string;
  outstanding: string;
  unit_cost: string;
  line_total: string;
}

export interface GrnLine {
  part: Ref;
  sku: string;
  quantity: string;
  unit_cost: string;
  discrepancy: string | null;
}

export interface PurchaseOrder extends PoListItem {
  notes: string | null;
  received_value: string;
  returned_value: string;
  lines: PoLine[];
  receipts: { id: UUID; grn_number: string; location: Ref; received_at: string; received_by: string; delivery_reference: string | null; supplier_invoice_reference: string | null; notes: string | null; total: string; lines: GrnLine[] }[];
  returns: { id: UUID; location: Ref; reason: string; reference: string | null; total: string; created_by: string; created_at: string; lines: GrnLine[] }[];
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  closed_reason: string | null;
  version: number;
  locations: Ref[];
  capabilities: { edit: boolean; approve: boolean; receive: boolean; return_goods: boolean; cancel: boolean; close: boolean };
}
