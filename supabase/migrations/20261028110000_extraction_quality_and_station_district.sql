-- v2.1.0: extraction quality check flags, and the station/district rule enforced by the database.
-- Additive: no existing row is changed by this migration (the two cases with a wrong district are
-- corrected by backend/scripts/fix_all_fulfilled.py --apply, with audit entries).

-- 1. Fields that contradict the FIR text they were extracted from (written by the quality check)
CREATE TABLE IF NOT EXISTS public.extraction_quality_flags (
    id varchar(36) PRIMARY KEY,
    case_id varchar(36) NOT NULL REFERENCES public.cases(id) ON DELETE CASCADE,
    document_id varchar(36),
    check_code varchar(40) NOT NULL,
    field_name varchar(50) NOT NULL,
    severity varchar(10) NOT NULL DEFAULT 'ERROR',
    stored_value text,
    source_value text,
    evidence text,
    message text NOT NULL,
    status varchar(12) NOT NULL DEFAULT 'OPEN',
    run_id varchar(36),
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_extraction_quality_flags_case_id ON public.extraction_quality_flags (case_id);
CREATE INDEX IF NOT EXISTS ix_extraction_quality_flags_check_code ON public.extraction_quality_flags (check_code);
CREATE INDEX IF NOT EXISTS ix_extraction_quality_flags_status ON public.extraction_quality_flags (status);
CREATE INDEX IF NOT EXISTS ix_extraction_quality_flags_run_id ON public.extraction_quality_flags (run_id);

-- Same posture as the other application tables: RLS enabled, no policies (only the backend's role)
ALTER TABLE public.extraction_quality_flags ENABLE ROW LEVEL SECURITY;

-- 2. Station master list lookups by name
CREATE INDEX IF NOT EXISTS ix_verified_stations_lower_name ON public.verified_stations (lower(station_name));

-- 3. A case at a station in the station master list must carry that station's district
CREATE OR REPLACE FUNCTION public.enforce_case_station_district() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    expected text;
BEGIN
    SELECT v.district INTO expected FROM public.verified_stations v
     WHERE lower(v.station_name) = lower(NEW.station) AND coalesce(v.is_active, true)
     LIMIT 1;
    IF expected IS NOT NULL AND lower(coalesce(NEW.district, '')) <> lower(expected) THEN
        RAISE EXCEPTION 'Station % belongs to % district in the station master list, not %',
            NEW.station, expected, NEW.district
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cases_station_district ON public.cases;
CREATE TRIGGER trg_cases_station_district
    BEFORE INSERT OR UPDATE OF station, district ON public.cases
    FOR EACH ROW EXECUTE FUNCTION public.enforce_case_station_district();
