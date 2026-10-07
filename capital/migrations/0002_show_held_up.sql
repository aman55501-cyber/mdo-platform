-- Ideas and calls are no longer filtered by what you hold; each row carries a `held` flag instead.
-- (Applied as capital_c0d_show_held_not_hide.) wb.desk_hidden from 0001 is now unused by the app.
create or replace view wb.ideas_view with (security_invoker = true) as
select i.id, wb.norm_symbol(i.symbol) as symbol, i.side, i.entry, i.stop, i.target, i.size_pct, i.horizon,
  i.thesis, i.status, i.run_date, (current_date - i.run_date) as age_days,
  pn.price, pn.price_time, pn.price_source,
  case when i.entry > 0 and pn.price is not null then round((pn.price / i.entry - 1) * 100, 2) end as pct_from_entry,
  exists (select 1 from wb.held_symbols h where h.symbol = wb.norm_symbol(i.symbol)) as held
from public.desk_ideas i
left join wb.price_now pn on pn.symbol = wb.norm_symbol(i.symbol)
where i.status in ('proposed','approved','open');

create or replace view wb.calls_view with (security_invoker = true) as
select c.id, c.caller, c.called_at, c.kind, c.action, c.symbol_raw, c.symbol, c.entry_low, c.entry_high, c.stop,
  c.targets, c.horizon, c.status, c.needs_review, c.source_msg_id,
  pn.price, pn.price_time, pn.price_source,
  case when c.entry_high > 0 and pn.price is not null then round((pn.price / c.entry_high - 1) * 100, 2) end as pct_from_entry,
  (c.symbol is null) as unresolved,
  exists (select 1 from wb.held_symbols h where h.symbol = coalesce(c.symbol, wb.norm_symbol(c.symbol_raw))) as held
from wb.calls c
left join wb.price_now pn on pn.symbol = c.symbol
where c.status in ('open','watching');
revoke all on wb.ideas_view, wb.calls_view from anon, authenticated;
