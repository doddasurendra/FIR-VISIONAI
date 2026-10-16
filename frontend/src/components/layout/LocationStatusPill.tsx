/**
 * LocationStatusPill
 * 
 * Displays advisory geolocation detection status in the government header ribbon.
 * Shows live status, detected district/confidence, and a confirmation modal.
 *
 * SECURITY: This component is purely advisory. It NEVER replaces the user's
 * authenticated jurisdictional scope. Authorized station/district/role remain
 * strictly from JWT token claims.
 */

import React, { useState } from 'react';
import {
  MapPin, Navigation, AlertTriangle, CheckCircle2,
  X, Loader2, ShieldCheck
} from 'lucide-react';
import { useGeolocationStation, LocationStatus } from '../../hooks/useGeolocationStation';
import api from '../../api/client';

interface LocationStatusPillProps {
  /** The user's authorized station from JWT (immutable authorization boundary) */
  authorizedStation?: string;
  /** The user's authorized district from JWT (immutable authorization boundary) */
  authorizedDistrict?: string;
}

export const LocationStatusPill: React.FC<LocationStatusPillProps> = ({
  authorizedStation,
  authorizedDistrict,
}) => {
  const geo = useGeolocationStation();
  const [showModal, setShowModal] = useState(false);
  const [loadingDistricts, setLoadingDistricts] = useState(false);
  const [availableDistricts, setAvailableDistricts] = useState<string[]>([]);
  const [availableStations, setAvailableStations] = useState<string[]>([]);
  const [manualDistrict, setManualDistrict] = useState('');
  const [manualStation, setManualStation] = useState('');

  const openModal = async () => {
    setShowModal(true);
    if (geo.status === 'idle') {
      geo.requestLocation();
    }
    // Fetch districts for manual selection if needed
    if (availableDistricts.length === 0) {
      setLoadingDistricts(true);
      try {
        const res = await api.get('/jurisdictions/districts');
        setAvailableDistricts(res.data || []);
      } catch {
        // fall through; will use geo.allDistricts
      } finally {
        setLoadingDistricts(false);
      }
    }
  };

  const handleManualDistrictChange = async (district: string) => {
    setManualDistrict(district);
    setManualStation('');
    if (district) {
      try {
        const res = await api.get(`/jurisdictions/stations?district=${encodeURIComponent(district)}`);
        setAvailableStations(res.data || []);
      } catch {
        setAvailableStations([]);
      }
    } else {
      setAvailableStations([]);
    }
  };

  const getPillContent = () => {
    switch (geo.status) {
      case 'idle':
        return null; // Don't show pill until user interacts
      case 'detecting':
        return (
          <span className="flex items-center gap-1 text-amber-300 text-[10px] font-medium">
            <Loader2 className="w-3 h-3 animate-spin" /> Detecting location...
          </span>
        );
      case 'awaiting_confirmation':
        return (
          <button
            onClick={openModal}
            className="flex items-center gap-1 text-amber-300 text-[10px] font-medium hover:text-amber-200 underline"
            title="Location detected — click to confirm your station"
          >
            <MapPin className="w-3 h-3" />
            Location detected — confirm station
          </button>
        );
      case 'confirmed':
        return (
          <span className="flex items-center gap-1 text-emerald-300 text-[10px] font-medium">
            <CheckCircle2 className="w-3 h-3" /> Confirmed station location
          </span>
        );
      case 'permission_denied':
        return (
          <button
            onClick={openModal}
            className="flex items-center gap-1 text-slate-400 text-[10px] hover:text-slate-300 underline"
            title="Location permission denied — click to manually select station"
          >
            <AlertTriangle className="w-3 h-3" /> Location permission required
          </button>
        );
      case 'unavailable':
      case 'error':
        return (
          <button
            onClick={openModal}
            className="flex items-center gap-1 text-slate-400 text-[10px] hover:text-slate-300 underline"
          >
            <MapPin className="w-3 h-3" /> Select station manually
          </button>
        );
      default:
        return null;
    }
  };

  const pillContent = getPillContent();

  const districtsToShow = geo.allDistricts.length > 0 ? geo.allDistricts : availableDistricts;

  return (
    <>
      {/* Detect Location Trigger Button (always visible in header) */}
      {geo.status === 'idle' && (
        <button
          onClick={openModal}
          title="Detect my station location (advisory)"
          className="flex items-center gap-1 text-emerald-200/60 hover:text-emerald-200 text-[10px] transition-colors"
        >
          <Navigation className="w-3 h-3" />
          <span className="hidden lg:inline">Detect station</span>
        </button>
      )}

      {/* Status pill when active */}
      {pillContent && (
        <div className="flex items-center">
          {pillContent}
        </div>
      )}

      {/* Location Confirmation Modal */}
      {showModal && (
        <div className="fixed inset-0 z-[100] bg-slate-900/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md border border-slate-200 overflow-hidden">
            {/* Modal Header */}
            <div className="bg-[#0f5132] text-white px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 bg-white/10 rounded-lg">
                  <MapPin className="w-4 h-4 text-emerald-200" />
                </div>
                <div>
                  <h3 className="font-bold text-sm">Station Location — Advisory</h3>
                  <p className="text-[11px] text-emerald-300">For informational display only</p>
                </div>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Security Notice */}
              <div className="flex items-start gap-2.5 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs">
                <ShieldCheck className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="text-amber-800 leading-relaxed">
                  <span className="font-bold">Security Notice: </span>
                  Your authorized jurisdiction is defined by your departmental credentials and cannot be changed here. This feature only provides an advisory location display.
                </div>
              </div>

              {/* Authorized Scope (immutable) */}
              {(authorizedStation || authorizedDistrict) && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs">
                  <p className="font-bold text-emerald-800 mb-1 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Your Authorized Jurisdiction (immutable)
                  </p>
                  <p className="text-emerald-700">
                    {authorizedStation ? `${authorizedStation}, ` : ''}{authorizedDistrict || ''}
                  </p>
                </div>
              )}

              {/* Detection Status */}
              {geo.status === 'detecting' && (
                <div className="flex items-center gap-2 text-sm text-slate-600 py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <span>Detecting your approximate location...</span>
                </div>
              )}

              {geo.status === 'awaiting_confirmation' && geo.detectedDistrict && (
                <div className="space-y-2">
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs">
                    <p className="font-bold text-blue-800 mb-1">Detected Approximate Location</p>
                    <div className="flex items-center justify-between">
                      <span className="text-blue-700">Nearest AP District:</span>
                      <span className="font-semibold text-blue-900">{geo.detectedDistrict}</span>
                    </div>
                    {geo.nearestDistanceKm !== null && (
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-blue-600">Distance to district centre:</span>
                        <span className="font-mono text-blue-800">{geo.nearestDistanceKm} km</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-0.5">
                      <span className="text-blue-600">Confidence:</span>
                      <span className={`font-bold ${geo.confidence === 'HIGH' ? 'text-emerald-700' : geo.confidence === 'MEDIUM' ? 'text-amber-700' : 'text-red-600'}`}>
                        {geo.confidence}
                      </span>
                    </div>
                  </div>
                  {geo.disclaimer && (
                    <p className="text-[10px] text-slate-500 leading-relaxed italic">{geo.disclaimer}</p>
                  )}
                </div>
              )}

              {(geo.status === 'permission_denied' || geo.status === 'unavailable' || geo.status === 'error') && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  <p className="font-semibold mb-1">
                    {geo.status === 'permission_denied' ? 'Location Permission Denied' : 'Location Unavailable'}
                  </p>
                  <p className="leading-relaxed">{geo.errorMessage}</p>
                </div>
              )}

              {/* Manual Station Selector Fallback */}
              <div className="border-t border-slate-100 pt-4 space-y-3">
                <p className="text-xs font-semibold text-slate-700">Manual District & Station Selection (Advisory)</p>
                {loadingDistricts ? (
                  <div className="text-xs text-slate-500 flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading district list...
                  </div>
                ) : (
                  <>
                    <select
                      value={manualDistrict}
                      onChange={(e) => handleManualDistrictChange(e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                    >
                      <option value="">Select a district…</option>
                      {districtsToShow.map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>

                    {manualStation !== undefined && availableStations.length > 0 && (
                      <select
                        value={manualStation}
                        onChange={(e) => setManualStation(e.target.value)}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                      >
                        <option value="">Select a station…</option>
                        {availableStations.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    )}
                  </>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => {
                    geo.requestLocation();
                  }}
                  disabled={geo.status === 'detecting'}
                  className="text-xs text-[#0f5132] hover:text-emerald-700 font-semibold underline flex items-center gap-1 disabled:opacity-50"
                >
                  <Navigation className="w-3 h-3" />
                  {geo.status === 'detecting' ? 'Detecting...' : 'Retry location detection'}
                </button>

                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      geo.clearLocation();
                      setManualDistrict('');
                      setManualStation('');
                      setShowModal(false);
                    }}
                    className="px-3 py-1.5 border border-slate-300 text-slate-600 rounded-lg text-xs hover:bg-slate-50"
                  >
                    Clear
                  </button>
                  <button
                    onClick={() => setShowModal(false)}
                    className="px-4 py-1.5 bg-[#0f5132] text-white rounded-lg text-xs font-semibold hover:bg-emerald-800 shadow-sm"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
