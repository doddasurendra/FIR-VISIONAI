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

export interface GeolocationStationResult {
  status: LocationStatus;
  detectedDistrict: string | null;
  candidateStations: string[];
  allDistricts: string[];
  nearestDistanceKm: number | null;
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
  const [allDistricts, setAllDistricts] = useState<string[]>([]);
  const [nearestDistanceKm, setNearestDistanceKm] = useState<number | null>(null);
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
        const { latitude, longitude } = position.coords;
        try {
          const res = await api.get('/jurisdictions/reverse-geocode', {
            params: { latitude: latitude.toFixed(5), longitude: longitude.toFixed(5) }
          });
          const data = res.data;
          setDetectedDistrict(data.detected_district);
          setCandidateStations(data.candidate_stations || []);
          setAllDistricts(data.all_districts || []);
          setNearestDistanceKm(data.nearest_distance_km);
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
        enableHighAccuracy: false,   // Wi-Fi network location acceptable
        timeout: 10000,
        maximumAge: 300000           // Cache for 5 minutes
      }
    );
  }, []);

  const clearLocation = useCallback(() => {
    setStatus('idle');
    setDetectedDistrict(null);
    setCandidateStations([]);
    setNearestDistanceKm(null);
    setConfidence(null);
    setDisclaimer(null);
    setErrorMessage(null);
  }, []);

  return {
    status,
    detectedDistrict,
    candidateStations,
    allDistricts,
    nearestDistanceKm,
    confidence,
    disclaimer,
    errorMessage,
    requestLocation,
    clearLocation,
  };
}
