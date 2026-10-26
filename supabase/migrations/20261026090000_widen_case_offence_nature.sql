-- Case confirmation failed with HTTP 500 ("value too long for type character varying(150)")
-- when the officer-reviewed offence allegation was longer than 150 characters.
-- varchar(150) -> text keeps every existing value unchanged; PostgreSQL does not rewrite the
-- table for this conversion, and no index, view, trigger or generated column depends on it.
ALTER TABLE public.cases ALTER COLUMN offence_nature TYPE text;
