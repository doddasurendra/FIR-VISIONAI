-- FIR VisionAI: label the earlier hand-written legal summaries as unverified (data change, no deletes).
-- Run as the table owner (see backend/scripts/apply_sql_migration.py). Re-runnable.
--
-- The 'legal' documents and legal_corpus sections created before the official-source import are short
-- paraphrases rendered into PDFs, not official text. They stay searchable, but are no longer presented
-- as verified official law. legal_corpus.verification_status is left unchanged because the application
-- uses it as the "active provision" flag (Act browser, section recommender); provenance is recorded in
-- the new source_type column instead.

update public.documents
set is_verified_official = false,
    source_type = 'UNVERIFIED',
    verification_note = 'Hand-written summary created during development; not the official text. Use the official source documents for legal decisions.'
where doc_category = 'LEGAL_ACT'
  and coalesce(source_type, 'UNVERIFIED') <> 'OFFICIAL';

update public.legal_corpus
set source_type = 'UNVERIFIED'
where source_type is null;
