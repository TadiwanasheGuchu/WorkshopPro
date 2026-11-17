-- Seed for the performance review: roughly three years of a busy single-branch workshop
-- (~30 jobs per working day). Run by scripts/perf/reset.sh on a database with one organisation.
BEGIN;
SELECT setseed(0.42);
CREATE TEMP TABLE ctx AS
SELECT o.id AS org, b.id AS branch, u.id AS usr
FROM organisations o JOIN branches b ON b.organisation_id = o.id JOIN users u ON u.organisation_id = o.id
LIMIT 1;

CREATE TEMP TABLE first_names(n) AS VALUES ('Johannes'),('Maria'),('Petrus'),('Anna'),('Tangeni'),('Ndapewa'),('Hendrik'),('Selma'),('Frans'),('Martha'),('Kaarina'),('Simon'),('Elina'),('Gerhard'),('Lahja'),('Tobias'),('Ruusa'),('David'),('Ester'),('Victor');
CREATE TEMP TABLE last_names(n) AS VALUES ('Shikongo'),('Nghidinwa'),('van Wyk'),('Amukoto'),('Shilongo'),('Kandjii'),('Haufiku'),('Nambahu'),('Mbumba'),('Muller'),('Iipinge'),('Shipanga'),('Kaapanda'),('Angula'),('Hamutenya'),('Swartbooi'),('Nujoma'),('Kambonde'),('Uushona'),('Beukes'),('Tjiriange'),('Engelbrecht'),('Hausiku'),('Nakale'),('Mweshida');
CREATE TEMP TABLE models(make, model) AS VALUES ('Toyota','Hilux'),('Toyota','Corolla'),('Toyota','Fortuner'),('Volkswagen','Polo'),('Nissan','Navara'),('Ford','Ranger'),('Isuzu','D-Max'),('Toyota','Land Cruiser'),('Mercedes-Benz','C-Class'),('Hyundai','i20'),('Kia','Picanto'),('BMW','3 Series');

INSERT INTO customers (id, organisation_id, customer_type, first_name, last_name, display_name, preferred_contact_method, created_at, updated_at)
SELECT gen_random_uuid(), ctx.org, 'individual', f.n, l.n, f.n || ' ' || l.n || ' ' || g, 'whatsapp',
       now() - (random() * interval '1095 days'), now()
FROM ctx, generate_series(1, 8000) g
CROSS JOIN LATERAL (SELECT n FROM first_names ORDER BY random() + g * 0 LIMIT 1) f
CROSS JOIN LATERAL (SELECT n FROM last_names ORDER BY random() + g * 0 LIMIT 1) l;

CREATE TEMP TABLE cust AS SELECT id, row_number() OVER (ORDER BY id) AS rn FROM customers;

INSERT INTO customer_contacts (id, organisation_id, customer_id, kind, value, is_primary)
SELECT gen_random_uuid(), ctx.org, c.id, 'phone', '+26481' || lpad((1000000 + c.rn)::text, 7, '0'), true FROM ctx, cust c;
INSERT INTO customer_contacts (id, organisation_id, customer_id, kind, value, is_primary)
SELECT gen_random_uuid(), ctx.org, c.id, 'email', 'customer' || c.rn || '@example.com', false FROM ctx, cust c WHERE c.rn % 8 < 5;

INSERT INTO vehicles (id, organisation_id, customer_id, registration_number, registration_key, make, model, year, created_at, updated_at)
SELECT gen_random_uuid(), ctx.org, c.id, 'N ' || g || ' W', 'N' || g || 'W', m.make, m.model, 2005 + (g % 19),
       now() - (random() * interval '1095 days'), now()
FROM ctx, generate_series(1, 10000) g
JOIN cust c ON c.rn = 1 + (g::bigint * 7919) % 8000
CROSS JOIN LATERAL (SELECT make, model FROM models ORDER BY random() + g * 0 LIMIT 1) m;

INSERT INTO vehicle_ownerships (id, organisation_id, vehicle_id, customer_id, started_at)
SELECT gen_random_uuid(), v.organisation_id, v.id, v.customer_id, v.created_at FROM vehicles v;

CREATE TEMP TABLE veh AS SELECT id, customer_id, row_number() OVER (ORDER BY id) AS rn FROM vehicles;

CREATE TEMP TABLE jobs AS
SELECT gen_random_uuid() AS id, g,
       now() - ((g::float / 30000) * interval '1095 days') AS received_at,
       CASE WHEN g > 29900 THEN (ARRAY['vehicle_received','inspection_pending','diagnosis_in_progress','awaiting_approval','awaiting_parts','repair_in_progress','quality_inspection','ready_for_collection'])[1 + g % 8]
            WHEN g % 50 = 0 THEN 'cancelled' ELSE 'completed' END AS status,
       v.id AS vehicle_id, v.customer_id
FROM generate_series(1, 30000) g JOIN veh v ON v.rn = 1 + (g::bigint * 104729) % 10000;
-- Newest jobs have the lowest g; make received_at increase with job number instead.
UPDATE jobs SET received_at = now() - (((30001 - g)::float / 30000) * interval '1095 days');

INSERT INTO job_cards (id, organisation_id, branch_id, job_number, customer_id, vehicle_id, complaint, status, priority,
                       received_at, collected_at, cancellation_reason, received_by_user_id, created_at, updated_at)
SELECT j.id, ctx.org, ctx.branch, 'JC-' || lpad(j.g::text, 6, '0'), j.customer_id, j.vehicle_id,
       'Service and check noise from front left', j.status, 'normal', j.received_at,
       CASE WHEN j.status = 'completed' THEN j.received_at + interval '2 days' END,
       CASE WHEN j.status = 'cancelled' THEN 'Customer withdrew' END,
       ctx.usr, j.received_at, j.received_at + interval '2 days'
FROM ctx, jobs j;

INSERT INTO job_status_history (id, organisation_id, job_card_id, from_status, to_status, changed_by_user_id, changed_at)
SELECT gen_random_uuid(), ctx.org, j.id, s.f, s.t, ctx.usr, j.received_at + s.o * interval '6 hours'
FROM ctx, jobs j
CROSS JOIN LATERAL (VALUES (NULL, 'vehicle_received', 0), ('vehicle_received', 'diagnosis_in_progress', 1),
                           ('diagnosis_in_progress', 'repair_in_progress', 2), ('repair_in_progress', j.status, 3)) s(f, t, o);

CREATE TEMP TABLE inv AS
SELECT gen_random_uuid() AS id, row_number() OVER (ORDER BY j.g) AS n, j.id AS job_id, j.customer_id,
       round((500 + random() * 14500)::numeric, 2) AS subtotal, j.received_at + interval '2 days' AS issued_at, j.g
FROM jobs j WHERE j.status = 'completed' AND j.g % 5 <> 0;

INSERT INTO invoices (id, organisation_id, branch_id, customer_id, job_card_id, status, invoice_number, issue_date, due_date,
                      currency_code, prices_include_tax, subtotal, tax_total, total, amount_paid, issued_at, issued_by_user_id, created_by_user_id, created_at, updated_at)
SELECT i.id, ctx.org, ctx.branch, i.customer_id, i.job_id, 'issued', 'INV-' || lpad(i.n::text, 6, '0'),
       i.issued_at::date, i.issued_at::date + 30, 'NAD', false, i.subtotal, round(i.subtotal * 0.15, 2),
       round(i.subtotal * 1.15, 2),
       CASE WHEN i.g % 20 = 1 THEN 0 WHEN i.g % 20 = 2 THEN round(i.subtotal * 0.5, 2) ELSE round(i.subtotal * 1.15, 2) END,
       i.issued_at, ctx.usr, ctx.usr, i.issued_at, i.issued_at
FROM ctx, inv i;

CREATE TEMP TABLE pay AS
SELECT gen_random_uuid() AS id, row_number() OVER (ORDER BY i.issue_date, i.id) AS n, i.id AS invoice_id, i.customer_id,
       i.amount_paid AS amount, i.issued_at + interval '1 day' AS received_at
FROM invoices i WHERE i.amount_paid > 0;

INSERT INTO payments (id, organisation_id, branch_id, customer_id, kind, receipt_number, method, amount, currency_code,
                      received_at, idempotency_key, request_fingerprint, recorded_by_user_id, created_at)
SELECT p.id, ctx.org, ctx.branch, p.customer_id, 'payment', 'RCT-' || lpad(p.n::text, 6, '0'),
       (ARRAY['cash','eft','card'])[1 + p.n % 3], p.amount, 'NAD', p.received_at, 'seed-' || p.n, 'seed', ctx.usr, p.received_at
FROM ctx, pay p;

INSERT INTO payment_allocations (id, organisation_id, payment_id, invoice_id, amount, created_by_user_id, created_at)
SELECT gen_random_uuid(), ctx.org, p.id, p.invoice_id, p.amount, ctx.usr, p.received_at FROM ctx, pay p;

INSERT INTO notifications (id, organisation_id, branch_id, customer_id, related_type, related_id, event, channel, recipient, body, status, created_at, sent_at)
SELECT gen_random_uuid(), ctx.org, ctx.branch, j.customer_id, 'job_card', j.id, e.event, 'whatsapp', '+264810000000', 'Seeded message',
       CASE WHEN j.g % 40 = 0 THEN 'failed' ELSE 'delivered' END, j.received_at + e.o * interval '1 day',
       j.received_at + e.o * interval '1 day'
FROM ctx, jobs j CROSS JOIN LATERAL (VALUES ('vehicle_received', 0), ('ready_for_collection', 2)) e(event, o);

INSERT INTO audit_logs (id, organisation_id, branch_id, actor_type, actor_user_id, action, entity_type, entity_id, summary, created_at)
SELECT gen_random_uuid(), ctx.org, ctx.branch, 'user', ctx.usr, a.action, 'job_card', j.id, 'Seeded event', j.received_at + a.o * interval '3 hours'
FROM ctx, jobs j CROSS JOIN LATERAL (VALUES ('job_card.created', 0), ('job_card.status_changed', 1), ('job_card.status_changed', 2),
  ('job_card.status_changed', 3), ('job_card.mechanic_assigned', 1), ('invoice.issued', 4), ('payment.recorded', 5),
  ('job_card.note_added', 2), ('inspection.submitted', 1), ('quotation.sent', 2), ('quotation.approved', 3), ('job_card.updated', 4)) a(action, o);

UPDATE document_sequences d SET next_number = x.n + 1 FROM (SELECT 'job_card' t, count(*) n FROM job_cards UNION ALL SELECT 'invoice', count(*) FROM invoices UNION ALL SELECT 'receipt', count(*) FROM payments) x WHERE d.document_type = x.t;
COMMIT;
ANALYZE;
SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE n_live_tup > 1000 ORDER BY 2 DESC;
