-- ==============================================================================
-- FIR SAHAYAK — SUPABASE POSTGRESQL PRODUCTION SCHEMA
-- Andhra Pradesh Prohibition & Excise Department
-- Unified First Information Report (u-FIR) Intelligence Platform
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Enable pgvector if available on the Supabase project
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "vector";
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgvector extension not installed or permission denied; continuing with text-based embeddings.';
END $$;

-- 2. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'STATION' CHECK (role IN ('STATION', 'DISTRICT', 'STATE')),
    district VARCHAR(50) NOT NULL,
    station VARCHAR(100),
    badge_number VARCHAR(50),
    designation VARCHAR(50) DEFAULT 'Excise Sub-Inspector',
    department VARCHAR(100) DEFAULT 'AP Prohibition & Excise Department',
    approval_status VARCHAR(20) NOT NULL DEFAULT 'APPROVED' CHECK (approval_status IN ('APPROVED', 'PENDING_APPROVAL', 'REJECTED')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_district ON users(district);
CREATE INDEX IF NOT EXISTS idx_users_station ON users(station);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 3. REFRESH TOKENS TABLE
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);

-- 4. CASES TABLE (u-FIR)
CREATE TABLE IF NOT EXISTS cases (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    fir_number VARCHAR(100) UNIQUE NOT NULL,
    year INTEGER NOT NULL,
    district VARCHAR(50) NOT NULL,
    station VARCHAR(100) NOT NULL,
    mandal VARCHAR(50),
    village VARCHAR(50),
    location_description TEXT,
    offence_date TIMESTAMPTZ,
    detection_date TIMESTAMPTZ,
    registration_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    offence_nature VARCHAR(150) NOT NULL,
    offence_category VARCHAR(100),
    contraband_type VARCHAR(100),
    seized_quantity DOUBLE PRECISION,
    seized_unit VARCHAR(20),
    vehicle_details VARCHAR(200),
    seizing_officer_name VARCHAR(100),
    seizing_officer_rank VARCHAR(50),
    witnesses_summary TEXT,
    narrative TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'ARCHIVED')),
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    archived_reason VARCHAR(255),
    archived_by VARCHAR(36),
    created_by VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cases_fir_number ON cases(fir_number);
CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district);
CREATE INDEX IF NOT EXISTS idx_cases_station ON cases(station);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);

-- 5. CASE PROVENANCE & HUMAN VERIFICATION FIELDS
CREATE TABLE IF NOT EXISTS case_fields (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,
    original_value TEXT,
    normalized_value TEXT,
    source_doc_id VARCHAR(36),
    page_number INTEGER,
    extraction_method VARCHAR(50) DEFAULT 'GEMINI_VISION',
    confidence_score DOUBLE PRECISION DEFAULT 1.0,
    verification_status VARCHAR(20) DEFAULT 'UNVERIFIED' CHECK (verification_status IN ('UNVERIFIED', 'VERIFIED', 'OVERRIDDEN')),
    human_override_value TEXT,
    verified_by VARCHAR(36),
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_fields_case_id ON case_fields(case_id);
CREATE INDEX IF NOT EXISTS idx_case_fields_field_name ON case_fields(field_name);

-- 6. DOCUMENTS TABLE (Evidence & Uploaded FIR PDFs)
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id VARCHAR(36) REFERENCES cases(id) ON DELETE SET NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    mime_type VARCHAR(100) DEFAULT 'application/pdf',
    physical_page_count INTEGER DEFAULT 1,
    is_scanned BOOLEAN DEFAULT FALSE,
    ingestion_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (ingestion_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    error_message TEXT,
    created_by VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);

-- 7. DOCUMENT PAGES TABLE (Physical Page Provenance)
CREATE TABLE IF NOT EXISTS document_pages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    physical_page_number INTEGER NOT NULL,
    printed_page_number INTEGER,
    raw_text TEXT,
    ocr_applied BOOLEAN DEFAULT FALSE,
    ocr_confidence DOUBLE PRECISION DEFAULT 1.0,
    is_unreadable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_pages_doc_id ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_document_pages_page_num ON document_pages(physical_page_number);

-- 8. DOCUMENT CHUNKS TABLE (PDF-Only Grounded RAG with exact page numbers)
CREATE TABLE IF NOT EXISTS document_chunks (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    physical_page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    char_start INTEGER DEFAULT 0,
    char_end INTEGER DEFAULT 0,
    embedding_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_page_num ON document_chunks(physical_page_number);

-- 9. ENTITIES TABLE (Syndicate & Accused Resolution)
CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    canonical_name VARCHAR(150) NOT NULL,
    entity_type VARCHAR(30) NOT NULL CHECK (entity_type IN ('PERSON', 'VEHICLE', 'LOCATION', 'ORGANIZATION')),
    aliases_json TEXT DEFAULT '[]',
    attributes_json TEXT DEFAULT '{}',
    risk_score DOUBLE PRECISION DEFAULT 0.0,
    risk_factors_json TEXT DEFAULT '[]',
    is_canonical BOOLEAN DEFAULT TRUE,
    merged_into_id VARCHAR(36) REFERENCES entities(id) ON DELETE SET NULL,
    verification_status VARCHAR(20) DEFAULT 'CONFIRMED' CHECK (verification_status IN ('CONFIRMED', 'REVIEW_PENDING', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entities_canonical_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_is_canonical ON entities(is_canonical);

-- 10. ENTITY MENTIONS TABLE
CREATE TABLE IF NOT EXISTS entity_mentions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    entity_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    mention_text VARCHAR(150) NOT NULL,
    role_in_case VARCHAR(50) DEFAULT 'ACCUSED',
    source_doc_id VARCHAR(36),
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_id ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_case_id ON entity_mentions(case_id);

-- 11. GRAPH EDGES TABLE (Multi-Station Syndicate Links)
CREATE TABLE IF NOT EXISTS graph_edges (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    source_entity_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    edge_type VARCHAR(50) DEFAULT 'CO_ACCUSED',
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    weight DOUBLE PRECISION DEFAULT 1.0,
    community_id INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_case_id ON graph_edges(case_id);

-- 12. LEGAL CORPUS TABLE
CREATE TABLE IF NOT EXISTS legal_corpus (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    act_name VARCHAR(150) NOT NULL,
    section_number VARCHAR(50) NOT NULL,
    section_title VARCHAR(200) NOT NULL,
    full_text TEXT NOT NULL,
    explanation TEXT,
    essential_ingredients_json TEXT DEFAULT '[]',
    penalty_text TEXT,
    effective_date VARCHAR(30),
    repeal_date VARCHAR(30),
    version VARCHAR(20) DEFAULT '1.0',
    jurisdiction VARCHAR(50) DEFAULT 'Andhra Pradesh',
    source_url VARCHAR(300),
    source_gazette VARCHAR(200),
    verification_status VARCHAR(20) DEFAULT 'VERIFIED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legal_corpus_act ON legal_corpus(act_name);
CREATE INDEX IF NOT EXISTS idx_legal_corpus_section ON legal_corpus(section_number);

-- 13. CASE LEGAL SECTIONS TABLE
CREATE TABLE IF NOT EXISTS case_legal_sections (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    legal_corpus_id VARCHAR(36) NOT NULL REFERENCES legal_corpus(id) ON DELETE CASCADE,
    act_name VARCHAR(150) NOT NULL,
    section_number VARCHAR(50) NOT NULL,
    section_title VARCHAR(200) NOT NULL,
    recommendation_type VARCHAR(30) DEFAULT 'AI_RECOMMENDED',
    confidence_score DOUBLE PRECISION DEFAULT 0.85,
    matched_facts_json TEXT DEFAULT '[]',
    missing_elements_json TEXT DEFAULT '[]',
    officer_decision VARCHAR(20) DEFAULT 'PENDING' CHECK (officer_decision IN ('ACCEPTED', 'REJECTED', 'PENDING')),
    decision_reason TEXT,
    reviewed_by VARCHAR(36),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_legal_sections_case_id ON case_legal_sections(case_id);

-- 14. TAMPER-EVIDENT RECURSIVE SHA-256 AUDIT LOG TABLE
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    entry_uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::text,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id VARCHAR(36) NOT NULL,
    actor_username VARCHAR(50) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    object_type VARCHAR(50) NOT NULL,
    object_id VARCHAR(36) NOT NULL,
    before_state_json TEXT,
    after_state_json TEXT,
    client_ip VARCHAR(50),
    previous_entry_hash VARCHAR(64) NOT NULL,
    entry_hash VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_object ON audit_log(object_type, object_id);

-- 15. CASE SUMMARIES, GENERATED DOCUMENTS, AND BULK JOBS
CREATE TABLE IF NOT EXISTS case_summaries (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    language VARCHAR(10) DEFAULT 'en',
    is_ai_generated BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generated_documents (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    doc_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'IN_REVIEW', 'APPROVED')),
    approved_by VARCHAR(36),
    approved_at TIMESTAMPTZ,
    pdf_path VARCHAR(500),
    created_by VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_approval_history (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    document_id VARCHAR(36) NOT NULL REFERENCES generated_documents(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    action VARCHAR(30) NOT NULL,
    officer_id VARCHAR(36) NOT NULL,
    comments TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bulk_jobs (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    total_records INTEGER DEFAULT 0,
    processed_records INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    errors_json TEXT DEFAULT '[]',
    user_id VARCHAR(36) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- 16. ROW-LEVEL SECURITY (RLS) POLICIES FOR JURISDICTION SCOPING
-- ==============================================================================
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Note: When connecting from FastAPI via service role or backend pool, RLS can be bypassed
-- or enforced via custom app claims (current_setting('app.current_user_role')).
-- The following policies demonstrate production-grade row security:

CREATE POLICY cases_select_policy ON cases
    FOR SELECT
    USING (
        current_setting('app.current_user_role', true) = 'STATE'
        OR (current_setting('app.current_user_role', true) = 'DISTRICT' AND district = current_setting('app.current_user_district', true))
        OR (current_setting('app.current_user_role', true) = 'STATION' AND station = current_setting('app.current_user_station', true))
        OR current_setting('app.current_user_role', true) IS NULL -- Fallback for backend superuser
    );

-- 17. SUPABASE PRIVATE STORAGE BUCKET CONFIGURATION
-- Run this in Supabase SQL editor to create the private 'evidence' bucket:
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'evidence',
    'evidence',
    false,
    52428800, -- 50MB limit
    ARRAY['application/pdf']
)
ON CONFLICT (id) DO NOTHING;
