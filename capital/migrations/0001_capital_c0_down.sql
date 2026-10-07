-- Reverses 0001_capital_c0_up.sql. Review before running: it drops the tables it created.
drop view if exists wb.desk_freshness, wb.by_bucket, wb.net_worth_lines, wb.balance_latest, wb.actions_view,
  wb.desk_hidden, wb.calls_view, wb.ideas_view, wb.held_symbols, wb.holdings_view, wb.price_now, wb.holdings_raw;
drop trigger if exists targets_audit on wb.targets;
drop function if exists wb.log_target_change();
drop function if exists wb.norm_symbol(text);
drop table if exists wb.target_history, wb.calls, wb.quotes, wb.manual_holdings, wb.portfolio_owner;
delete from wb.job_schedule where job in ('bantu_calls','quote_poll');
delete from wb.conflicts where subject like 'Aditi Investments holdings%';
