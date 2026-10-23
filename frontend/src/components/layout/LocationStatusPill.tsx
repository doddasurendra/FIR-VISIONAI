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
  X, Loader2, ShieldCheck, ShieldAlert, Building2, Compass, Clock
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
                <div className="flex items-center gap-2 text-sm text-slate-600 py-4 justify-center bg-slate-50 rounded-lg border border-slate-200">
                  <Loader2 className="w-5 h-5 animate-spin text-[#0f5132]" />
                  <span className="font-medium text-xs">Acquiring high-precision GPS coordinates...</span>
                </div>
              )}

              {/* Exact Station Match View */}
              {geo.status === 'awaiting_confirmation' && geo.exactStation && (
                <div className="space-y-3">
                  <div className="p-3.5 bg-emerald-50/70 border border-emerald-300 rounded-lg space-y-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded">
                          <CheckCircle2 className="w-3 h-3 text-emerald-700" /> Exact Station Detected
                        </span>
                        <h4 className="font-bold text-slate-900 text-sm mt-1">{geo.exactStation.station_name}</h4>
                        <p className="text-[11px] font-mono text-emerald-900 font-semibold">{geo.exactStation.station_code}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-[11px] font-semibold text-emerald-800 bg-white border border-emerald-200 px-2 py-0.5 rounded shadow-sm">
                          {geo.exactStation.distance_km < 1
                            ? `${geo.exactStation.distance_meters} m`
                            : `${geo.exactStation.distance_km} km`}
                        </span>
                      </div>
                    </div>

                    <div className="text-xs text-slate-700 space-y-0.5 pt-1 border-t border-emerald-200/60">
                      {geo.exactStation.mandal && (
                        <div><span className="font-semibold text-slate-600">Mandal:</span> {geo.exactStation.mandal}</div>
                      )}
                      {geo.exactStation.locality && (
                        <div><span className="font-semibold text-slate-600">Locality:</span> {geo.exactStation.locality}</div>
                      )}
                      {geo.exactStation.address && (
                        <div className="text-[11px] text-slate-600 italic">{geo.exactStation.address}</div>
                      )}
                    </div>

                    {/* Technical telemetry */}
                    <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1.5 border-t border-emerald-200/60">
                      <span className="flex items-center gap-1">
                        <Compass className="w-3 h-3 text-emerald-600" />
                        {geo.exactStation.latitude.toFixed(5)}°N, {geo.exactStation.longitude.toFixed(5)}°E
                      </span>
                      {geo.accuracyMeters !== null && (
                        <span>GPS Accuracy: ±{geo.accuracyMeters}m</span>
                      )}
                      {geo.detectionTimestamp && (
                        <span>{new Date(geo.detectionTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                      )}
                    </div>
                  </div>

                  {/* Officer Authorization Banner */}
                  {geo.exactStation.is_officer_authorized ? (
                    <div className="flex items-start gap-2 p-2.5 bg-green-50 border border-green-200 rounded-lg text-xs text-green-900">
                      <ShieldCheck className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <span className="font-bold">Officer Authorized: </span>
                        Detected station matches your assigned department post ({authorizedStation || authorizedDistrict || 'Authorized Station'}).
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2 p-2.5 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900">
                      <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <span className="font-bold">Jurisdiction Notice: </span>
                        Detected station is outside your assigned post ({authorizedStation || authorizedDistrict || 'Assigned Station'}). Case registration remains locked to your authorized jurisdiction.
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Nearby Candidate Stations (when no single exact station or multiple candidates) */}
              {geo.status === 'awaiting_confirmation' && !geo.exactStation && geo.detectedDistrict && (
                <div className="space-y-2">
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-blue-800">Detected District Area</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${geo.confidence === 'HIGH' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                        {geo.confidence} CONFIDENCE
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-blue-700">Nearest District:</span>
                      <span className="font-semibold text-blue-900">{geo.detectedDistrict}</span>
                    </div>
                    {geo.nearestDistanceKm !== null && (
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-blue-600">Distance to station cluster:</span>
                        <span className="font-mono text-blue-800">{geo.nearestDistanceKm} km</span>
                      </div>
                    )}
                  </div>

                  {geo.candidateStationObjects && geo.candidateStationObjects.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Candidate Stations Nearby</p>
                      <div className="max-h-36 overflow-y-auto space-y-1 border border-slate-200 rounded-lg p-1 bg-slate-50">
                        {geo.candidateStationObjects.slice(0, 4).map((c) => (
                          <div key={c.station_code || c.station_name} className="flex items-center justify-between p-1.5 bg-white rounded border border-slate-200 text-xs">
                            <div>
                              <div className="font-semibold text-slate-800">{c.station_name}</div>
                              <div className="text-[10px] text-slate-500">{c.district} {c.mandal ? `• ${c.mandal}` : ''}</div>
                            </div>
                            <span className="text-[10px] font-mono text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded">
                              {c.distance_km} km
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

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

              {/* Manual Station Selector Fallback with High-Contrast Visible Options */}
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
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs bg-white text-slate-900 focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                    >
                      <option value="" className="bg-white text-slate-700">Select a district…</option>
                      {districtsToShow.map((d) => (
                        <option key={d} value={d} className="bg-white text-slate-900 py-1">{d}</option>
                      ))}
                    </select>

                    {manualStation !== undefined && availableStations.length > 0 && (
                      <select
                        value={manualStation}
                        onChange={(e) => setManualStation(e.target.value)}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs bg-white text-slate-900 focus:ring-2 focus:ring-[#0f5132] focus:outline-none"
                      >
                        <option value="" className="bg-white text-slate-700">Select a station…</option>
                        {availableStations.map((s) => (
                          <option key={s} value={s} className="bg-white text-slate-900 py-1">{s}</option>
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
