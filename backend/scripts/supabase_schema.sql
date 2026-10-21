-- ==================================================================
-- FIR VisionAI / Unified FIR & AI-Powered Case Intelligence Platform
-- Supabase PostgreSQL Complete Production Schema
-- ==================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Table: audit_log
CREATE TABLE audit_log (
	id SERIAL NOT NULL, 
	entry_uuid VARCHAR(36) NOT NULL, 
	timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	actor_username VARCHAR(50) NOT NULL, 
	action_type VARCHAR(50) NOT NULL, 
	object_type VARCHAR(50) NOT NULL, 
	object_id VARCHAR(36) NOT NULL, 
	before_state_json TEXT, 
	after_state_json TEXT, 
	client_ip VARCHAR(50), 
	previous_entry_hash VARCHAR(64) NOT NULL, 
	entry_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (entry_uuid)
);

-- Table: bulk_jobs
CREATE TABLE bulk_jobs (
	id VARCHAR(36) NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	file_type VARCHAR(20) NOT NULL, 
	file_hash VARCHAR(64) NOT NULL, 
	total_records INTEGER, 
	processed_records INTEGER, 
	success_count INTEGER, 
	failure_count INTEGER, 
	status VARCHAR(20) NOT NULL, 
	errors_json TEXT, 
	user_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: cases
CREATE TABLE cases (
	id VARCHAR(36) NOT NULL, 
	fir_number VARCHAR(100) NOT NULL, 
	year INTEGER NOT NULL, 
	district VARCHAR(50) NOT NULL, 
	station VARCHAR(100) NOT NULL, 
	mandal VARCHAR(50), 
	village VARCHAR(50), 
	location_description TEXT, 
	offence_date TIMESTAMP WITHOUT TIME ZONE, 
	detection_date TIMESTAMP WITHOUT TIME ZONE, 
	registration_date TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	offence_nature VARCHAR(150) NOT NULL, 
	offence_category VARCHAR(100), 
	contraband_type VARCHAR(100), 
	seized_quantity FLOAT, 
	seized_unit VARCHAR(20), 
	vehicle_details VARCHAR(200), 
	seizing_officer_name VARCHAR(100), 
	seizing_officer_rank VARCHAR(50), 
	witnesses_summary TEXT, 
	narrative TEXT, 
	status VARCHAR(20) NOT NULL, 
	is_archived BOOLEAN NOT NULL, 
	archived_reason VARCHAR(255), 
	archived_by VARCHAR(36), 
	created_by VARCHAR(36) NOT NULL, 
	classification_status VARCHAR(20), 
	classification_confidence FLOAT, 
	classification_source VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: entities
CREATE TABLE entities (
	id VARCHAR(36) NOT NULL, 
	canonical_name VARCHAR(150) NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	aliases_json TEXT, 
	attributes_json TEXT, 
	risk_score FLOAT, 
	risk_factors_json TEXT, 
	is_canonical BOOLEAN, 
	merged_into_id VARCHAR(36), 
	verification_status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(merged_into_id) REFERENCES entities (id) ON DELETE SET NULL
);

-- Table: extraction_configs
CREATE TABLE extraction_configs (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	version INTEGER NOT NULL, 
	schema_json TEXT NOT NULL, 
	instructions TEXT, 
	sarvam_config_id VARCHAR(100), 
	is_active BOOLEAN, 
	created_by VARCHAR(36), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: fir_folders
CREATE TABLE fir_folders (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	slug VARCHAR(80) NOT NULL, 
	description TEXT, 
	color_code VARCHAR(20), 
	icon_name VARCHAR(50), 
	group_label VARCHAR(50), 
	parent_id VARCHAR(36), 
	is_restricted BOOLEAN, 
	required_role VARCHAR(20), 
	is_system BOOLEAN, 
	sort_order INTEGER, 
	is_active BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES fir_folders (id) ON DELETE SET NULL
);

-- Table: legal_corpus
CREATE TABLE legal_corpus (
	id VARCHAR(36) NOT NULL, 
	act_name VARCHAR(150) NOT NULL, 
	section_number VARCHAR(50) NOT NULL, 
	section_title VARCHAR(200) NOT NULL, 
	full_text TEXT NOT NULL, 
	explanation TEXT, 
	essential_ingredients_json TEXT, 
	penalty_text TEXT, 
	effective_date VARCHAR(30), 
	repeal_date VARCHAR(30), 
	version VARCHAR(20), 
	jurisdiction VARCHAR(50), 
	source_url VARCHAR(300), 
	source_gazette VARCHAR(200), 
	verification_status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: refresh_tokens
CREATE TABLE refresh_tokens (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	token VARCHAR(255) NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	is_revoked BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: users
CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	email VARCHAR(100) NOT NULL, 
	full_name VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	district VARCHAR(50) NOT NULL, 
	station VARCHAR(100), 
	badge_number VARCHAR(50), 
	designation VARCHAR(50), 
	department VARCHAR(100), 
	approval_status VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_login TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: case_fields
CREATE TABLE case_fields (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	field_name VARCHAR(50) NOT NULL, 
	original_value TEXT, 
	normalized_value TEXT, 
	source_doc_id VARCHAR(36), 
	page_number INTEGER, 
	extraction_method VARCHAR(50), 
	confidence_score FLOAT, 
	verification_status VARCHAR(20), 
	human_override_value TEXT, 
	verified_by VARCHAR(36), 
	verified_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: case_folder_assignments
CREATE TABLE case_folder_assignments (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	folder_id VARCHAR(36) NOT NULL, 
	assigned_by VARCHAR(36), 
	is_primary BOOLEAN, 
	confidence_score FLOAT, 
	assignment_source VARCHAR(20), 
	notes TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(folder_id) REFERENCES fir_folders (id) ON DELETE CASCADE
);

-- Table: case_legal_sections
CREATE TABLE case_legal_sections (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	legal_corpus_id VARCHAR(36) NOT NULL, 
	act_name VARCHAR(150) NOT NULL, 
	section_number VARCHAR(50) NOT NULL, 
	section_title VARCHAR(200) NOT NULL, 
	recommendation_type VARCHAR(30), 
	confidence_score FLOAT, 
	matched_facts_json TEXT, 
	missing_elements_json TEXT, 
	officer_decision VARCHAR(20), 
	decision_reason TEXT, 
	reviewed_by VARCHAR(36), 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(legal_corpus_id) REFERENCES legal_corpus (id) ON DELETE CASCADE
);

-- Table: case_summaries
CREATE TABLE case_summaries (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	summary_text TEXT NOT NULL, 
	language VARCHAR(10), 
	is_ai_generated BOOLEAN, 
	version INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: documents
CREATE TABLE documents (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36), 
	original_filename VARCHAR(255) NOT NULL, 
	stored_path VARCHAR(500) NOT NULL, 
	file_hash VARCHAR(64) NOT NULL, 
	mime_type VARCHAR(100), 
	physical_page_count INTEGER, 
	is_scanned BOOLEAN, 
	ingestion_status VARCHAR(20) NOT NULL, 
	sarvam_job_id VARCHAR(100), 
	error_message TEXT, 
	created_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE SET NULL
);

-- Table: entity_mentions
CREATE TABLE entity_mentions (
	id VARCHAR(36) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	mention_text VARCHAR(150) NOT NULL, 
	role_in_case VARCHAR(50), 
	source_doc_id VARCHAR(36), 
	page_number INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entities (id) ON DELETE CASCADE, 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: generated_documents
CREATE TABLE generated_documents (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	doc_type VARCHAR(50) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	content TEXT NOT NULL, 
	version INTEGER, 
	status VARCHAR(20) NOT NULL, 
	approved_by VARCHAR(36), 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	pdf_path VARCHAR(500), 
	created_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: graph_edges
CREATE TABLE graph_edges (
	id VARCHAR(36) NOT NULL, 
	source_entity_id VARCHAR(36) NOT NULL, 
	target_entity_id VARCHAR(36) NOT NULL, 
	edge_type VARCHAR(50), 
	case_id VARCHAR(36) NOT NULL, 
	weight FLOAT, 
	community_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_entity_id) REFERENCES entities (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_entity_id) REFERENCES entities (id) ON DELETE CASCADE, 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: workflow_executions
CREATE TABLE workflow_executions (
	id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	stage VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	retry_count INTEGER, 
	result_summary TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

-- Table: document_approval_history
CREATE TABLE document_approval_history (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	action VARCHAR(30) NOT NULL, 
	officer_id VARCHAR(36) NOT NULL, 
	comments TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES generated_documents (id) ON DELETE CASCADE
);

-- Table: document_chunks
CREATE TABLE document_chunks (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	physical_page_number INTEGER NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	chunk_text TEXT NOT NULL, 
	char_start INTEGER, 
	char_end INTEGER, 
	embedding_json TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

-- Table: document_pages
CREATE TABLE document_pages (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	physical_page_number INTEGER NOT NULL, 
	printed_page_number INTEGER, 
	raw_text TEXT, 
	ocr_applied BOOLEAN, 
	ocr_confidence FLOAT, 
	is_unreadable BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);

-- Table: extraction_runs
CREATE TABLE extraction_runs (
	id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	config_id VARCHAR(36), 
	config_version INTEGER, 
	status VARCHAR(20) NOT NULL, 
	raw_extracted_json TEXT, 
	reviewed_extracted_json TEXT, 
	case_id VARCHAR(36), 
	sarvam_job_id VARCHAR(100), 
	error_message TEXT, 
	created_by VARCHAR(36), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	FOREIGN KEY(config_id) REFERENCES extraction_configs (id) ON DELETE SET NULL, 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE SET NULL
);

-- ==================================================================
-- Recommended Storage Bucket (Run in Supabase SQL Editor if needed)
-- ==================================================================
INSERT INTO storage.buckets (id, name, public) VALUES ('evidence', 'evidence', false)
ON CONFLICT (id) DO NOTHING;

