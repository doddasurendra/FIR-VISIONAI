/**
 * useGeolocationStation
 * 
 * Advisory-only location hook for FIR VisionAI.
 * Uses the browser Geolocation API to detect approximate physical location,
 * then resolves the closest Andhra Pradesh district and candidate excise stations
 * via the backend /jurisdictions/reverse-geocode endpoint.
 *
 * CRITICAL SECURITY NOTE:
 * Detected location is PURELY INFORMATIONAL/ADVISORY. It is NEVER used for
 * authorization decisions. The authenticated user's assigned role, station, and
 * district from the JWT token remain the sole source of access control.
 */

import { useState, useEffect, useCallback } from 'react';
import api from '../api/client';

export type LocationStatus =
  | 'idle'
  | 'detecting'
  | 'awaiting_confirmation'
  | 'confirmed'
  | 'permission_denied'
  | 'unavailable'
  | 'error';

export interface VerifiedStationDetails {
  id?: string;
  station_code: string;
  station_name: string;
  district: string;
  mandal?: string;
  locality?: string;
  address?: string;
  latitude: number;
  longitude: number;
  distance_km: number;
  distance_meters: number;
  is_officer_authorized?: boolean;
}

export interface OfficerAuthInfo {
  username: string;
  role: string;
  assigned_district: string;
  assigned_station: string;
  is_authorized_station: boolean;
}

export interface GeolocationStationResult {
  status: LocationStatus;
  detectedDistrict: string | null;
  candidateStations: string[];
  candidateStationObjects: VerifiedStationDetails[];
  exactStation: VerifiedStationDetails | null;
  officerAuth: OfficerAuthInfo | null;
  matchType: 'EXACT_MATCH' | 'NEARBY_CANDIDATES' | 'DISTRICT_LEVEL' | null;
  allDistricts: string[];
  nearestDistanceKm: number | null;
  accuracyMeters: number | null;
  detectionTimestamp: string | null;
  confidence: 'HIGH' | 'MEDIUM' | 'APPROXIMATE' | null;
  disclaimer: string | null;
  errorMessage: string | null;
  requestLocation: () => void;
  clearLocation: () => void;
}

export function useGeolocationStation(): GeolocationStationResult {
  const [status, setStatus] = useState<LocationStatus>('idle');
  const [detectedDistrict, setDetectedDistrict] = useState<string | null>(null);
  const [candidateStations, setCandidateStations] = useState<string[]>([]);
  const [candidateStationObjects, setCandidateStationObjects] = useState<VerifiedStationDetails[]>([]);
  const [exactStation, setExactStation] = useState<VerifiedStationDetails | null>(null);
  const [officerAuth, setOfficerAuth] = useState<OfficerAuthInfo | null>(null);
  const [matchType, setMatchType] = useState<'EXACT_MATCH' | 'NEARBY_CANDIDATES' | 'DISTRICT_LEVEL' | null>(null);
  const [allDistricts, setAllDistricts] = useState<string[]>([]);
  const [nearestDistanceKm, setNearestDistanceKm] = useState<number | null>(null);
  const [accuracyMeters, setAccuracyMeters] = useState<number | null>(null);
  const [detectionTimestamp, setDetectionTimestamp] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<'HIGH' | 'MEDIUM' | 'APPROXIMATE' | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const requestLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus('unavailable');
      setErrorMessage('Browser Geolocation API is not supported. Please manually select your station.');
      return;
    }

    setStatus('detecting');
    setErrorMessage(null);

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        try {
          const res = await api.get('/jurisdictions/reverse-geocode', {
            params: {
              latitude: latitude.toFixed(6),
              longitude: longitude.toFixed(6),
              accuracy: accuracy ? Math.round(accuracy) : undefined
            }
          });
          const data = res.data;
          setDetectedDistrict(data.detected_district);
          setCandidateStations(data.candidate_stations || []);
          setCandidateStationObjects(data.candidate_station_objects || []);
          setExactStation(data.exact_station || null);
          setOfficerAuth(data.officer_auth || null);
          setMatchType(data.match_type || null);
          setAllDistricts(data.all_districts || []);
          setNearestDistanceKm(data.nearest_distance_km);
          setAccuracyMeters(data.accuracy_meters ?? (accuracy ? Math.round(accuracy) : null));
          setDetectionTimestamp(data.detection_timestamp || new Date().toISOString());
          setConfidence(data.confidence);
          setDisclaimer(data.disclaimer);
          setStatus('awaiting_confirmation');
        } catch (err: any) {
          console.error('Reverse geocode failed:', err);
          setStatus('error');
          setErrorMessage('Could not resolve location to a station. Please select your station manually.');
        }
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus('permission_denied');
          setErrorMessage('Location permission denied. Please select your station manually.');
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setStatus('unavailable');
          setErrorMessage('Location unavailable. Please select your station manually.');
        } else {
          setStatus('error');
          setErrorMessage('Location detection timed out. Please select your station manually.');
        }
      },
      {
        enableHighAccuracy: true,   // High-precision GPS coordinates
        timeout: 12000,
        maximumAge: 60000            // Cache for 1 minute max for active accuracy
      }
    );
  }, []);

  const clearLocation = useCallback(() => {
    setStatus('idle');
    setDetectedDistrict(null);
    setCandidateStations([]);
    setCandidateStationObjects([]);
    setExactStation(null);
    setOfficerAuth(null);
    setMatchType(null);
    setNearestDistanceKm(null);
    setAccuracyMeters(null);
    setDetectionTimestamp(null);
    setConfidence(null);
    setDisclaimer(null);
    setErrorMessage(null);
  }, []);

  return {
    status,
    detectedDistrict,
    candidateStations,
    candidateStationObjects,
    exactStation,
    officerAuth,
    matchType,
    allDistricts,
    nearestDistanceKm,
    accuracyMeters,
    detectionTimestamp,
    confidence,
    disclaimer,
    errorMessage,
    requestLocation,
    clearLocation,
  };
}
