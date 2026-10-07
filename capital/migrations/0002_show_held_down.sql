-- Restores the filtered versions from 0001. A view cannot lose a column via CREATE OR REPLACE, so this drops
-- and recreates both (the Supabase tool asks for confirmation on DROP). Review before running.
drop view if exists wb.ideas_view, wb.calls_view;
-- then re-run the ideas_view and calls_view definitions from 0001_capital_c0_up.sql
