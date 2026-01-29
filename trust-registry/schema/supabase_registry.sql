-- Enable Row Level Security (Multi-Tenancy Enforcer)
alter table agents enable row level security;
alter table rules enable row level security;

-- 1. Agents Table
create table agents (
  agent_id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null, -- Multi-Tenant Key
  name text,
  provider text,
  tier text,
  auth_scope text,
  public_key text,
  status text default 'Active',
  full_schema_json jsonb,
  created_at timestamptz default now()
);

-- RLS Policy: Tenants can only see their own agents
create policy "Tenants can only view their own agents"
on agents for select
to authenticated
using (auth.uid() = tenant_id); -- Assuming auth.uid mapping, or use a custom claim

-- 2. Rules Table
create table rules (
  rule_id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  natural_language text,
  logic_json jsonb,
  priority int default 1,
  status text default 'Active',
  created_at timestamptz default now()
);

-- RLS Policy
create policy "Tenants can only see their own rules"
on rules for all
to authenticated
using (auth.uid() = tenant_id);

-- 3. Realtime Publication
-- Allow Realtime to listen to changes
alter publication supabase_realtime add table rules;
