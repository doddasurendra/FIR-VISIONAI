-- IPC -> BNS correspondence table (corpus/ipc_bns_mapping.json), used to suggest the BNS counterpart
-- of an IPC section an FIR cites for an incident on or after 1 July 2024.
-- Additive only: no existing table or row is modified. Rows are loaded by
-- backend/scripts/import_legal_corpus_v2.py --apply (which also adds the new legal_corpus rows:
-- IPC 468/471, BNS 336(3)/340(2), IT Act, NDPS, Arms Act and MV Act provisions).
CREATE TABLE IF NOT EXISTS public.ipc_bns_mapping (
    id varchar(36) PRIMARY KEY,
    ipc_section varchar(50) NOT NULL,
    ipc_title varchar(200),
    bns_section varchar(50),
    bns_title varchar(200),
    note text,
    source varchar(300) NOT NULL,
    source_url varchar(300),
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    CONSTRAINT uq_ipc_bns_mapping_ipc_section UNIQUE (ipc_section)
);
CREATE INDEX IF NOT EXISTS ix_ipc_bns_mapping_ipc_section ON public.ipc_bns_mapping (ipc_section);
CREATE INDEX IF NOT EXISTS ix_ipc_bns_mapping_bns_section ON public.ipc_bns_mapping (bns_section);

-- Lookups of a provision by Act and section number (the recommender reads only the provisions it needs)
CREATE INDEX IF NOT EXISTS ix_legal_corpus_act_section ON public.legal_corpus (act_name, section_number);

-- Same posture as the other application tables: only the backend's own role reads and writes;
-- the public API roles get no access (RLS enabled, no policies).
ALTER TABLE public.ipc_bns_mapping ENABLE ROW LEVEL SECURITY;
