-- COA — schema.sql (Postgres / Supabase) — Fase 1
-- Rodar no SQL Editor do Supabase. Auth de usuários é a tabela nativa auth.users.

-- ===== ASSOCIAÇÕES (base pré-alimentada) =====
create table associations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  name_normalized text not null,          -- para matching
  address text, city text, county text, zip text,
  unit_count int,
  dbpr_number text,                        -- registro no DBPR
  sunbiz_doc_number text,                  -- corporação
  status text,                             -- ativa/inativa (Sunbiz)
  registered_agent text,
  match_confidence numeric,                -- 0-1 do matching entre bases
  created_at timestamptz default now()
);
create index on associations (name_normalized);
create index on associations (zip);

create table association_directors (
  id uuid primary key default gen_random_uuid(),
  association_id uuid references associations(id),
  name text, title text, source text, as_of date
);

create table managers (                    -- administradoras / CAM
  id uuid primary key default gen_random_uuid(),
  name text not null, license_number text, license_type text,
  disciplinary_history boolean default false
);

create table association_managers (        -- vínculo, com histórico
  association_id uuid references associations(id),
  manager_id uuid references managers(id),
  start_date date, end_date date,
  primary key (association_id, manager_id, start_date)
);

create table public_complaints (           -- queixas públicas CTMH importadas
  id uuid primary key default gen_random_uuid(),
  association_id uuid references associations(id),
  year int, category text, source text
);

-- ===== USUÁRIOS (complemento ao auth.users do Supabase) =====
create table profiles (
  user_id uuid primary key references auth.users(id),
  full_name text,
  phone text,
  role text not null default 'owner' check (role in ('owner','staff','admin')),
  created_at timestamptz default now()
);

create table user_units (                  -- um usuário pode ter mais de uma unidade
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id),
  association_id uuid references associations(id),
  unit_number text not null,
  owner_verified boolean default false,    -- após revisão do comprovante
  created_at timestamptz default now()
);

-- ===== CASOS (o núcleo do sistema) =====
create table cases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id),
  user_unit_id uuid references user_units(id),
  association_id uuid references associations(id),
  module text not null check (module in ('A','B1','B2','C','D','E','F')),
  case_type text not null,                 -- ex.: records_request, mgmt_contract_request, budget_review
  status text not null default 'open' check (status in
    ('open','responded_verifying','escalated','resolved','partial','non_responsive','closed_referred')),
  target_document text,                    -- o que foi pedido (quando aplicável)
  deadline_date date,                      -- prazo legal calculado
  linked_case_id uuid references cases(id),-- vinculação (mesmo prédio, mesmo problema)
  created_at timestamptz default now(),
  closed_at timestamptz
);
create index on cases (association_id, status);
create index on cases (deadline_date);

create table case_events (                 -- linha do tempo imutável do caso
  id uuid primary key default gen_random_uuid(),
  case_id uuid references cases(id),
  event_type text not null,                -- created, letter_generated, sent, delivery_confirmed,
                                           -- response_received, deadline_warning, deadline_missed,
                                           -- escalated_notice, escalated_ctmh, coa_contact, status_change, note
  detail jsonb,
  actor text not null default 'system',    -- system | user | staff
  created_at timestamptz default now()
);

create table documents (                   -- todo arquivo do sistema (Storage guarda o binário)
  id uuid primary key default gen_random_uuid(),
  case_id uuid references cases(id),
  user_id uuid references auth.users(id),
  association_id uuid references associations(id),
  doc_type text not null,                  -- budget, mgmt_contract, letter_out, response_in,
                                           -- proof_of_ownership, reserve_study, proxy, other
  storage_path text not null,
  original_filename text,
  uploaded_at timestamptz default now()
);

-- ===== MÓDULO F =====
create table budget_analyses (
  id uuid primary key default gen_random_uuid(),
  case_id uuid references cases(id),
  association_id uuid references associations(id),
  budget_document_id uuid references documents(id),
  contract_document_id uuid references documents(id),   -- quando cruzamento
  budget_year int,
  extraction_ok boolean,                   -- V1-V4 passaram?
  validation_notes jsonb,                  -- somas que não fecharam, contradições
  findings jsonb,                          -- lista de achados nas 4 camadas
  report_text text,                        -- relatório final entregue
  model_version text,
  created_at timestamptz default now()
);

create table unit_prices (                 -- preços unitários informados (teste de realidade)
  id uuid primary key default gen_random_uuid(),
  association_id uuid references associations(id),
  price_type text not null,                -- valet_guest, pet_fee, screening, dockage, etc.
  amount numeric not null,
  reported_by uuid references auth.users(id),
  reported_at timestamptz default now()
);

-- ===== CAMADA 5 — PERFIL/INTELIGÊNCIA (interno) =====
create table association_metrics (
  association_id uuid primary key references associations(id),
  cases_total int default 0,
  cases_records int default 0,
  avg_response_days numeric,
  pct_responded_on_time numeric,
  non_responsive_count int default 0,
  last_case_at timestamptz,
  risk_flag text                            -- normal | slow | non_responsive (calculado por job)
);

-- ===== SEGURANÇA (Row Level Security) =====
alter table cases enable row level security;
alter table documents enable row level security;
alter table user_units enable row level security;
alter table budget_analyses enable row level security;

create policy own_cases on cases for all
  using (user_id = auth.uid() or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy own_docs on documents for all
  using (user_id = auth.uid() or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy own_units on user_units for all
  using (user_id = auth.uid() or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy own_analyses on budget_analyses for select
  using (exists (select 1 from cases c where c.id = budget_analyses.case_id and c.user_id = auth.uid())
      or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
-- associations, managers, metrics: leitura pública de associations; metrics restrito a staff.
alter table association_metrics enable row level security;
create policy staff_metrics on association_metrics for all
  using (exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));

-- ===== v2.1 — dados públicos adicionais =====
alter table associations add column if not exists project_number text;
alter table associations add column if not exists file_number text;
alter table associations add column if not exists recorded_date date;
alter table associations add column if not exists sirs_filed boolean;
alter table associations add column if not exists sirs_filed_period text;   -- 'pre-2025-07' | '2025-07+'

create table if not exists association_payments (   -- Payment History (5 anos) do DBPR
  id uuid primary key default gen_random_uuid(),
  association_id uuid references associations(id),
  project_number text,
  billing_year int,
  amount_billed numeric,
  amount_paid numeric,
  amount_due numeric
);
create index if not exists idx_pay_assoc on association_payments (association_id, billing_year);

-- ===== v2.2 — import idempotente (scripts/import_dbpr.py) =====
-- Project Number do DBPR é único no cadastro (confirmado nos extratos reais);
-- o import usa upsert por esses campos e pode ser re-executado sem duplicar.
create unique index if not exists uq_assoc_project on associations (project_number);
create unique index if not exists uq_manager_license on managers (license_number);

-- ===== v2.3 — endurecimento RLS (revisão de segurança 2026-07) =====
-- Regra geral: escrita nas tabelas de referência e nos registros de sistema é
-- feita SOMENTE pela service role (que ignora RLS). Clientes anon/autenticados
-- só têm o que as políticas abaixo concedem.

-- profiles: sem RLS aqui, qualquer cliente com a anon key podia se promover a
-- staff/admin (todas as outras políticas confiam em profiles.role).
alter table profiles enable row level security;
create policy profile_read_own on profiles for select using (user_id = auth.uid());
-- criação de perfil e mudança de papel: só via service role (sem política de escrita).

-- case_events: linha do tempo imutável — leitura pelo dono do caso ou staff;
-- escrita só pela service role (nenhuma política de insert/update/delete).
alter table case_events enable row level security;
create policy case_events_read on case_events for select using (
  exists (select 1 from cases c where c.id = case_events.case_id and c.user_id = auth.uid())
  or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));

-- cases: substituir o FOR ALL por políticas por comando — dono não deleta caso
-- (a trilha do case_events depende dele); delete fica sem política = negado.
drop policy own_cases on cases;
create policy cases_read on cases for select using (
  user_id = auth.uid()
  or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy cases_insert on cases for insert with check (user_id = auth.uid());
create policy cases_update on cases for update using (
  user_id = auth.uid()
  or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));

-- documents: dono do caso também enxerga documentos gerados pelo sistema/staff
-- no caso dele (a política antiga filtrava só por user_id do documento).
drop policy own_docs on documents;
create policy docs_read on documents for select using (
  user_id = auth.uid()
  or exists (select 1 from cases c where c.id = documents.case_id and c.user_id = auth.uid())
  or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy docs_insert on documents for insert with check (user_id = auth.uid());

-- user_units: usuário não pode se auto-verificar (owner_verified é decisão do staff).
drop policy own_units on user_units;
create policy units_read on user_units for select using (
  user_id = auth.uid()
  or exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create policy units_insert on user_units for insert with check (user_id = auth.uid() and owner_verified = false);
create policy units_update_staff on user_units for update using (
  exists (select 1 from profiles p where p.user_id = auth.uid() and p.role in ('staff','admin')));
create unique index if not exists uq_user_unit on user_units (user_id, association_id, unit_number);

-- budget_analyses: leitura já coberta por own_analyses; escrita só service role (intencional).

-- Tabelas de referência: RLS ligado com leitura adequada; escrita só service role (import).
alter table associations enable row level security;
create policy assoc_read on associations for select using (true);          -- busca pública de prédios
alter table managers enable row level security;
create policy managers_read on managers for select using (true);
alter table association_managers enable row level security;
create policy assoc_mgr_read on association_managers for select using (true);
alter table association_directors enable row level security;
create policy assoc_dir_read on association_directors for select using (true);
alter table public_complaints enable row level security;
create policy complaints_read on public_complaints for select using (auth.uid() is not null);
alter table association_payments enable row level security;
create policy payments_read on association_payments for select using (auth.uid() is not null);
alter table unit_prices enable row level security;
create policy unit_prices_read on unit_prices for select using (auth.uid() is not null);
create policy unit_prices_insert on unit_prices for insert with check (reported_by = auth.uid());
