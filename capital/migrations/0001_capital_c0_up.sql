-- Capital & Shares — C0 data model (additive only; nothing existing is altered or dropped).
-- Reuses: public.holdings (Angel pull), public.desk_ideas, public.wa_messages, wb.accounts/balances/
-- assets/liabilities/targets/owners. Down script: 0001_capital_c0_down.sql.
-- wb is not exposed over PostgREST; every object below is service-role / direct-DB only.

-- 1. portfolio -> owner (holdings.portfolio is the broker client code) ---------------------------
create table if not exists wb.portfolio_owner (
  portfolio text primary key,
  owner_id  text not null references wb.owners(id),
  broker    text,
  source    text not null,
  note      text
);
alter table wb.portfolio_owner enable row level security;
insert into wb.portfolio_owner (portfolio, owner_id, broker, source, note)
values ('A1504046','aditi_inv','angelone','build spec 6 Oct 2026: Aditi Investments = Angel A1504046',
        'scope is derived from owner kind (partnership => company); open conflict asks the owner to confirm')
on conflict (portfolio) do nothing;

-- 2. holdings the owner states by hand until the HDFC export ingest exists -----------------------
create table if not exists wb.manual_holdings (
  id        bigint generated always as identity primary key,
  owner_id  text not null references wb.owners(id),
  symbol    text not null,                 -- NSE ticker, e.g. COALINDIA (no -EQ)
  isin      text,
  qty       numeric,
  avg_price numeric,
  broker    text,
  source    text not null default 'owner-stated',
  stated_on date not null default current_date,
  active    boolean not null default true,
  unique (owner_id, symbol)
);
alter table wb.manual_holdings enable row level security;

-- 3. latest quotes (upserted by capital/jobs/quote_poll.py during market hours) -----------------
create table if not exists wb.quotes (
  symbol     text not null,                -- normalised: no -EQ suffix
  exchange   text not null default 'NSE',
  isin       text,
  ltp        numeric not null check (ltp > 0),
  prev_close numeric check (prev_close > 0),
  quote_time timestamptz not null,
  source     text not null,
  fetched_at timestamptz not null default now(),
  primary key (symbol, exchange)
);
alter table wb.quotes enable row level security;

-- 4. calls parsed from a caller's WhatsApp messages ------------------------------------------------
create table if not exists wb.calls (
  id            bigint generated always as identity primary key,
  source_msg_id bigint not null unique,    -- public.wa_messages.id  (the evidence)
  wa_account    text,
  caller        text not null,
  called_at     timestamptz not null,
  kind          text not null default 'call' check (kind in ('call','declared')),
  action        text not null check (action in ('ADD','BUY','SELL','TRIM','EXIT','HOLD','INFO')),
  symbol_raw    text not null,
  symbol        text,                      -- resolved to a known ticker, else null
  entry_low     numeric,
  entry_high    numeric,
  stop          numeric,
  targets       numeric[] not null default '{}',
  horizon       text,
  extractor     text not null default 'rule',
  confidence    numeric,
  needs_review  boolean not null default true,
  status        text not null default 'open'
                check (status in ('open','watching','booked','stopped','expired','dismissed')),
  outcome       jsonb,
  reviewed_at   timestamptz,
  created_at    timestamptz not null default now()
);
create index if not exists calls_called_at_idx on wb.calls (called_at desc);
alter table wb.calls enable row level security;

-- 5. every change to a plan level is recorded --------------------------------------------------------
create table if not exists wb.target_history (
  id         bigint generated always as identity primary key,
  target_id  bigint,
  symbol     text,
  changed_at timestamptz not null default now(),
  changed_by text default current_user,
  op         text,
  old_row    jsonb,
  new_row    jsonb,
  reason     text
);
alter table wb.target_history enable row level security;

create or replace function wb.log_target_change() returns trigger
language plpgsql set search_path = wb, pg_temp as $$
begin
  if tg_op = 'INSERT' then
    insert into wb.target_history (target_id, symbol, op, new_row) values (new.id, new.symbol, 'INSERT', to_jsonb(new));
  else
    insert into wb.target_history (target_id, symbol, op, old_row, new_row) values (new.id, new.symbol, 'UPDATE', to_jsonb(old), to_jsonb(new));
  end if;
  return new;
end $$;
-- create-or-replace (not drop+create): the Supabase migration tool blocks DROP statements pending a confirmation
create or replace trigger targets_audit after insert or update on wb.targets
  for each row execute function wb.log_target_change();

-- 6. symbol normaliser: "COALINDIA-EQ" / "Coal India" -> COALINDIA / COALINDIA -----------------------
create or replace function wb.norm_symbol(s text) returns text
language sql immutable set search_path = pg_catalog as $$
  select upper(regexp_replace(regexp_replace(coalesce(s,''), '-(EQ|BE|BZ|SM|ST)$', '', 'i'), '[^A-Za-z0-9]', '', 'g'))
$$;

-- 7. holdings: latest pull per portfolio, deduped, priced, owner/scope attached -------------------
create or replace view wb.holdings_raw with (security_invoker = true) as
with latest as (select portfolio, max(as_of) as_of from public.holdings group by portfolio)
select distinct on (h.portfolio, coalesce(h.isin, h.symbol))
  h.portfolio, h.broker, h.symbol as raw_symbol, wb.norm_symbol(h.symbol) as symbol, h.isin,
  h.qty, h.avg_price, h.ltp as pull_ltp,
  nullif(h.raw->>'close','')::numeric as pull_prev_close,
  h.raw->>'symboltoken' as symboltoken, coalesce(h.raw->>'exchange','NSE') as exchange,
  h.as_of, h.source
from public.holdings h join latest l on l.portfolio = h.portfolio and l.as_of = h.as_of
order by h.portfolio, coalesce(h.isin, h.symbol), h.id desc;

-- newest price per symbol: a quote only wins if it is newer than the holdings pull
create or replace view wb.price_now with (security_invoker = true) as
select distinct on (symbol) symbol, isin, price, prev_close, price_time, price_source from (
  select q.symbol, q.isin, q.ltp as price, q.prev_close, q.quote_time as price_time, q.source as price_source from wb.quotes q
  union all
  select r.symbol, r.isin, r.pull_ltp, r.pull_prev_close, r.as_of, 'holdings-pull' from wb.holdings_raw r where r.pull_ltp > 0
) p order by symbol, price_time desc;

create or replace view wb.holdings_view with (security_invoker = true) as
select r.portfolio, r.broker, r.symbol, r.isin, r.qty, r.avg_price,
  pn.price, pn.price_time, pn.price_source, pn.prev_close,
  round(r.qty * pn.price, 2) as market_value,
  round(r.qty * r.avg_price, 2) as invested,
  case when r.avg_price > 0 then round((pn.price / r.avg_price - 1) * 100, 2) end as pnl_pct,
  case when pn.prev_close > 0 then round((pn.price / pn.prev_close - 1) * 100, 2) end as day_change_pct,
  r.as_of as pulled_at, po.owner_id, o.name as owner_name,
  case when o.kind in ('individual','huf') then 'personal' when o.id is null then 'unassigned' else 'company' end as scope
from wb.holdings_raw r
left join wb.price_now pn on pn.symbol = r.symbol
left join wb.portfolio_owner po on po.portfolio = r.portfolio
left join wb.owners o on o.id = po.owner_id;

-- everything the owner already holds: ingested holdings + hand-stated ones
create or replace view wb.held_symbols with (security_invoker = true) as
select symbol, isin, owner_id, 'ingested:' || portfolio as via from wb.holdings_view
union
select wb.norm_symbol(symbol), isin, owner_id, 'owner-stated' from wb.manual_holdings where active;

-- 8. desk: trade ideas and calls, with already-held stocks removed ---------------------------------
create or replace view wb.ideas_view with (security_invoker = true) as
select i.id, wb.norm_symbol(i.symbol) as symbol, i.side, i.entry, i.stop, i.target, i.size_pct, i.horizon,
  i.thesis, i.status, i.run_date, (current_date - i.run_date) as age_days,
  pn.price, pn.price_time, pn.price_source,
  case when i.entry > 0 and pn.price is not null then round((pn.price / i.entry - 1) * 100, 2) end as pct_from_entry
from public.desk_ideas i
left join wb.price_now pn on pn.symbol = wb.norm_symbol(i.symbol)
where i.status in ('proposed','approved','open')
  and not exists (select 1 from wb.held_symbols h where h.symbol = wb.norm_symbol(i.symbol));

create or replace view wb.calls_view with (security_invoker = true) as
select c.id, c.caller, c.called_at, c.kind, c.action, c.symbol_raw, c.symbol, c.entry_low, c.entry_high, c.stop,
  c.targets, c.horizon, c.status, c.needs_review, c.source_msg_id,
  pn.price, pn.price_time, pn.price_source,
  case when c.entry_high > 0 and pn.price is not null then round((pn.price / c.entry_high - 1) * 100, 2) end as pct_from_entry,
  (c.symbol is null) as unresolved
from wb.calls c
left join wb.price_now pn on pn.symbol = c.symbol
where c.status in ('open','watching')
  and not exists (select 1 from wb.held_symbols h
                  where h.symbol = coalesce(c.symbol, wb.norm_symbol(c.symbol_raw)));

-- how many ideas/calls were hidden because the stock is already held (shown on the Desk)
create or replace view wb.desk_hidden with (security_invoker = true) as
select
 (select count(*) from public.desk_ideas i where i.status in ('proposed','approved','open')
    and exists (select 1 from wb.held_symbols h where h.symbol = wb.norm_symbol(i.symbol))) as ideas_hidden,
 (select count(*) from wb.calls c where c.status in ('open','watching')
    and exists (select 1 from wb.held_symbols h where h.symbol = coalesce(c.symbol, wb.norm_symbol(c.symbol_raw)))) as calls_hidden;

-- 9. plan levels: flag exact crossings only (no invented "near" threshold) ----------------------------
create or replace view wb.actions_view with (security_invoker = true) as
select t.id, t.symbol, t.status, t.buy_below, t.add_below, t.target, t.trim_above, t.thesis,
  pn.price, pn.price_time, pn.price_source,
  case when pn.price is null then 'NO_PRICE'
       when t.trim_above is not null and pn.price >= t.trim_above then 'ABOVE_TRIM'
       when t.target     is not null and pn.price >= t.target     then 'AT_TARGET'
       when t.buy_below  is not null and pn.price <= t.buy_below  then 'BELOW_BUY'
       when t.add_below  is not null and pn.price <= t.add_below  then 'BELOW_ADD'
  end as crossing,
  (t.buy_below is null and t.add_below is null and t.target is null and t.trim_above is null) as inputs_missing
from wb.targets t left join wb.price_now pn on pn.symbol = wb.norm_symbol(t.symbol)
where t.status in ('draft','approved');

-- 10. money: latest balance per account (final beats provisional on the same date) -----------------------
create or replace view wb.balance_latest with (security_invoker = true) as
select distinct on (b.account_id) b.account_id, a.owner_id, a.type, a.institution, a.last4, a.scope,
  b.as_of, b.amount, b.status, b.source, b.evidence, b.bucket_id, b.captured_at
from wb.balances b join wb.accounts a on a.id = b.account_id
where a.active
order by b.account_id, b.as_of desc, (b.status = 'final') desc, b.captured_at desc;

-- one tall view; the app sums it by owner/scope. Unassigned accounts never enter a total.
create or replace view wb.net_worth_lines with (security_invoker = true) as
select owner_id, scope, case when type in ('bank') then 'cash' else 'other_balances' end as line,
       amount, status, as_of, 'balance:' || account_id::text as ref
from wb.balance_latest where scope <> 'unassigned' and type not in ('loan','las','card')
union all
select owner_id, scope, 'holdings', market_value, 'provisional', pulled_at::date, 'holdings:' || portfolio
from wb.holdings_view where scope <> 'unassigned' and market_value is not null
union all
select a.owner_id, case when o.kind in ('individual','huf') then 'personal' else 'company' end, 'other_assets',
       a.value, case when a.basis = 'market' then 'final' else 'provisional' end, a.as_of, 'asset:' || a.id::text
from wb.assets a join wb.owners o on o.id = a.owner_id where a.value is not null
union all
select l.owner_id, case when o.kind in ('individual','huf') then 'personal' else 'company' end, 'liabilities',
       -l.outstanding, 'final', l.as_of, 'liability:' || l.id::text
from wb.liabilities l join wb.owners o on o.id = l.owner_id where l.outstanding is not null;

create or replace view wb.by_bucket with (security_invoker = true) as
select coalesce(bucket_id, 'unbucketed') as bucket_id, sum(amount) as amount, count(*) as lines
from (
  select bucket_id, amount from wb.balance_latest where scope <> 'unassigned' and type not in ('loan','las','card')
  union all
  select t.bucket_id, h.market_value from wb.holdings_view h left join wb.targets t on wb.norm_symbol(t.symbol) = h.symbol
  where h.scope <> 'unassigned' and h.market_value is not null
  union all
  select bucket_id, value from wb.assets where value is not null
) x group by 1;

-- 11. freshness: the Desk shows how old each input is ---------------------------------------------------
create or replace view wb.desk_freshness with (security_invoker = true) as
select 'holdings_pull'::text as source, max(as_of) as last_at from public.holdings
union all select 'quotes', max(quote_time) from wb.quotes
union all select 'bantu_chat', max(sent_at) from public.wa_messages where chat_name ilike 'Bantu%' and not from_me
union all select 'bank_balances', max(captured_at) from wb.balances;

-- 12. job registry: shipped inactive so the deadman does not page for jobs that are not deployed yet --------
insert into wb.job_schedule (job, description, stale_after_minutes, dead_after_minutes, active) values
 ('bantu_calls', 'Parse Bantu Mausaji messages into wb.calls', 90, 720, false),
 ('quote_poll',  'Intraday quotes for held + idea + call symbols (market hours)', 2880, 5760, false)
on conflict (job) do nothing;

-- 13. open decision for the owner (conflicts, never guessed) ------------------------------------------------
insert into wb.conflicts (subject, value_a, source_a, value_b, source_b)
select 'Aditi Investments holdings (Angel A1504046): personal or company scope?',
       'company (owner kind = partnership)', 'derived from wb.owners.kind',
       'owner has not confirmed', 'user'
where not exists (select 1 from wb.conflicts where subject like 'Aditi Investments holdings%');

revoke all on wb.portfolio_owner, wb.manual_holdings, wb.quotes, wb.calls, wb.target_history from anon, authenticated;
revoke all on wb.holdings_raw, wb.price_now, wb.holdings_view, wb.held_symbols, wb.ideas_view, wb.calls_view,
  wb.desk_hidden, wb.actions_view, wb.balance_latest, wb.net_worth_lines, wb.by_bucket, wb.desk_freshness from anon, authenticated;
