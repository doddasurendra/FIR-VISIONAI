-- Multilingual AI summaries of historical FIR records (FIR documents and registered cases).
-- One row per record and language; source_hash marks a summary stale when its source changes.
-- Additive only: no existing table or row is modified. case_summaries is kept as it is.
CREATE TABLE IF NOT EXISTS public.fir_summaries (
    id varchar(36) PRIMARY KEY,
    record_key varchar(50) NOT NULL,
    document_id varchar(36) REFERENCES public.documents(id) ON DELETE CASCADE,
    case_id varchar(36) REFERENCES public.cases(id) ON DELETE CASCADE,
    language varchar(5) NOT NULL,
    status varchar(20) NOT NULL,
    summary_json text,
    summary_text text,
    citations_json text,
    source_hash varchar(64),
    source_chars integer,
    model varchar(60),
    version integer NOT NULL DEFAULT 1,
    error_message text,
    generated_by varchar(36),
    generated_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT uq_fir_summaries_record_language UNIQUE (record_key, language),
    CONSTRAINT ck_fir_summaries_language CHECK (language IN ('en', 'te', 'hi')),
    CONSTRAINT ck_fir_summaries_source CHECK (document_id IS NOT NULL OR case_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_fir_summaries_record_key ON public.fir_summaries (record_key);
CREATE INDEX IF NOT EXISTS ix_fir_summaries_document_id ON public.fir_summaries (document_id);
CREATE INDEX IF NOT EXISTS ix_fir_summaries_case_id ON public.fir_summaries (case_id);
CREATE INDEX IF NOT EXISTS ix_fir_summaries_status ON public.fir_summaries (status);

-- Same posture as the other application tables: only the backend's own role reads and writes;
-- the public API roles get no access.
ALTER TABLE public.fir_summaries ENABLE ROW LEVEL SECURITY;
