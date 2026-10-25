-- FIR VisionAI: Knowledge Base / hybrid RAG upgrade, part 2 of 2.
-- Must run as the role that owns the application tables (the backend's database user,
-- fir_app_user); Supabase's postgres role is not the owner and cannot alter these tables.
-- Requires part 1 (20261025120000_kb_rag_extensions.sql). Additive and re-runnable: no table or
-- column is dropped, renamed or retyped, and no rows are deleted.

-- 1. Source provenance and index state on documents
alter table public.documents
  add column if not exists source_type varchar(20) default 'UNVERIFIED',
  add column if not exists record_kind varchar(20),
  add column if not exists source_url varchar(500),
  add column if not exists issuing_authority varchar(255),
  add column if not exists reference_number varchar(100),
  add column if not exists jurisdiction varchar(100),
  add column if not exists publication_date varchar(30),
  add column if not exists commencement_date varchar(30),
  add column if not exists legal_status varchar(20),
  add column if not exists language varchar(20),
  add column if not exists last_verified_at timestamp,
  add column if not exists verification_note text,
  add column if not exists index_status varchar(20) default 'NOT_INDEXED',
  add column if not exists indexed_chunk_count integer default 0,
  add column if not exists embedded_chunk_count integer default 0,
  add column if not exists embedding_model varchar(100),
  add column if not exists indexed_at timestamp;

create index if not exists ix_documents_source_type on public.documents (source_type);
create index if not exists ix_documents_legal_status on public.documents (legal_status);
create index if not exists ix_documents_index_status on public.documents (index_status);
create index if not exists ix_documents_category_archived on public.documents (doc_category, is_archived);

-- 2. Chunk structure, ranked full-text search and embeddings
alter table public.document_chunks
  add column if not exists section_ref varchar(100),
  add column if not exists section_title varchar(300),
  add column if not exists embedding extensions.vector(768);

alter table public.document_chunks
  add column if not exists content_tsv tsvector
    generated always as (to_tsvector('english',
      coalesce(section_ref, '') || ' ' || coalesce(section_title, '') || ' ' || coalesce(chunk_text, ''))) stored;

create index if not exists ix_document_chunks_section_ref on public.document_chunks (section_ref);
create index if not exists idx_document_chunks_content_tsv on public.document_chunks using gin (content_tsv);
create index if not exists idx_document_chunks_embedding_hnsw
  on public.document_chunks using hnsw (embedding extensions.vector_cosine_ops);

-- 3. Legal provision provenance
alter table public.legal_corpus
  add column if not exists source_type varchar(20),
  add column if not exists physical_page_number integer,
  add column if not exists source_checksum varchar(64),
  add column if not exists last_verified_at timestamp;
create index if not exists ix_legal_corpus_source_type on public.legal_corpus (source_type);

-- 4. Ingestion jobs (status history, failures, retries); owned by the application role
create table if not exists public.ingestion_jobs (
  id varchar(36) primary key,
  document_id varchar(36) not null references public.documents (id) on delete cascade,
  status varchar(20) not null default 'QUEUED',
  stage varchar(30),
  trigger varchar(30),
  pages_total integer default 0,
  pages_with_text integer default 0,
  chunks_written integer default 0,
  chunks_embedded integer default 0,
  error_message text,
  warnings_json text,
  started_at timestamp,
  finished_at timestamp,
  created_by varchar(36),
  created_at timestamp not null default now(),
  updated_at timestamp not null default now()
);
create index if not exists ix_ingestion_jobs_document_id on public.ingestion_jobs (document_id);
create index if not exists ix_ingestion_jobs_status on public.ingestion_jobs (status);

-- 5. Index state for existing documents. Documents whose only stored text is the placeholder that
--    older pipeline versions wrote when OCR failed have no real text, so they need review.
update public.documents d
set indexed_chunk_count = (select count(*) from public.document_chunks c where c.document_id = d.id),
    index_status = case
      when d.ingestion_status <> 'COMPLETED' then 'NOT_INDEXED'
      when not exists (
        select 1 from public.document_chunks c
        where c.document_id = d.id
          and c.chunk_text not like 'GOVERNMENT OF ANDHRA PRADESH - LAW ENFORCEMENT EVIDENCE RECORD%'
          and c.chunk_text not like '[Physical Page % Official Evidence Record]%'
      ) then 'NEEDS_REVIEW'
      else 'INDEXED'
    end
where d.index_status is null or d.index_status = 'NOT_INDEXED';

-- 6. Row Level Security. The backend connects as the table owner, which bypasses RLS, so the
--    application is unaffected; Supabase's public API roles get no row access.
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' and tableowner = current_user loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;
