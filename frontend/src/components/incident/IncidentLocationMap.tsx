import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import api from '../../api/client';
import {
  MapPin,
  Navigation,
  CheckCircle2,
  Edit2,
  Save,
  Eye,
  Loader2,
  AlertTriangle,
  RefreshCw,
  X,
  ExternalLink,
  FileText,
} from 'lucide-react';

// ── Fix Leaflet's broken default marker icon when bundled by Vite ──────────
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// ── Custom coloured markers ────────────────────────────────────────────────
const greenIcon = new L.Icon({
  iconUrl:
    'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const orangeIcon = new L.Icon({
  iconUrl:
    'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-orange.png',
  shadowUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const redIcon = new L.Icon({
  iconUrl:
    'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl:
    'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

// ── Types ──────────────────────────────────────────────────────────────────
interface LocationData {
  incident_place_raw?: string;
  incident_location_normalized?: string;
  incident_village?: string;
  incident_mandal?: string;
  incident_district?: string;
  incident_state?: string;
  incident_pincode?: string;
  incident_landmark?: string;
  incident_latitude?: number | null;
  incident_longitude?: number | null;
  incident_location_confidence?: number;
  incident_location_source_doc_id?: string;
  incident_location_source_page?: number;
  incident_location_evidence_passage?: string;
  incident_location_geocoder_status?: string;
  incident_location_verified?: boolean;
  incident_location_verified_by?: string;
  incident_location_verified_at?: string;
  directions_url?: string;
  is_approximate?: boolean;
  display_address?: string;
}

interface IncidentLocationMapProps {
  caseId: string;
  firNumber?: string;
  readOnly?: boolean;
}

// ── Helper ─────────────────────────────────────────────────────────────────
function statusBadge(status?: string) {
  const s = (status || '').toUpperCase();
  if (s === 'EXACT' || s === 'MANUAL_CONFIRMED')
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
        <CheckCircle2 className="w-3 h-3" /> {s === 'EXACT' ? 'Exact Match' : 'Confirmed'}
      </span>
    );
  if (s === 'APPROXIMATE')
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
        <AlertTriangle className="w-3 h-3" /> Approximate
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
      Unresolved
    </span>
  );
}

// ── Component ──────────────────────────────────────────────────────────────
export const IncidentLocationMap: React.FC<IncidentLocationMapProps> = ({
  caseId,
  firNumber,
  readOnly = false,
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  const [locationData, setLocationData] = useState<LocationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editAddress, setEditAddress] = useState('');
  const [geocoding, setGeocoding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);

  // ── Draft edit state (lat/lng can be adjusted by dragging marker) ────────
  const [draftLat, setDraftLat] = useState<number | null>(null);
  const [draftLng, setDraftLng] = useState<number | null>(null);

  // ── Fetch location from backend ──────────────────────────────────────────
  const fetchLocation = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/cases/${caseId}/location`);
      setLocationData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load incident location.');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchLocation();
  }, [fetchLocation]);

  // ── Initialise / update Leaflet map ─────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current || loading) return;

    const lat = locationData?.incident_latitude ?? null;
    const lng = locationData?.incident_longitude ?? null;
    const hasCoords = lat !== null && lng !== null;
    const center: L.LatLngExpression = hasCoords ? [lat!, lng!] : [15.9129, 79.7400]; // AP centre
    const zoom = hasCoords ? 13 : 7;

    if (!mapInstanceRef.current) {
      // Create map
      const map = L.map(mapRef.current, { zoomControl: true }).setView(center, zoom);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map);
      mapInstanceRef.current = map;
    } else {
      mapInstanceRef.current.setView(center, zoom);
    }

    // Remove old marker
    if (markerRef.current) {
      markerRef.current.remove();
      markerRef.current = null;
    }

    if (hasCoords) {
      const status = (locationData?.incident_location_geocoder_status || '').toUpperCase();
      const icon =
        status === 'EXACT' || status === 'MANUAL_CONFIRMED'
          ? greenIcon
          : status === 'APPROXIMATE'
          ? orangeIcon
          : redIcon;

      const marker = L.marker([lat!, lng!], { icon, draggable: !readOnly && editMode })
        .addTo(mapInstanceRef.current!)
        .bindPopup(
          `<div style="font-size:12px;min-width:180px">
            <strong>${firNumber ? `FIR ${firNumber}` : 'Incident Location'}</strong><br/>
            <span style="color:#64748b">${locationData?.incident_place_raw || 'No raw text'}</span><br/>
            <hr style="margin:4px 0"/>
            <span>Status: <b>${status || 'Unknown'}</b></span><br/>
            <span>Confidence: <b>${((locationData?.incident_location_confidence || 0) * 100).toFixed(0)}%</b></span>
          </div>`
        );

      // Update draft coords when marker is dragged
      marker.on('dragend', (e: L.LeafletEvent) => {
        const pos = (e as any).target.getLatLng();
        setDraftLat(pos.lat);
        setDraftLng(pos.lng);
      });

      markerRef.current = marker;
    }
  }, [locationData, loading, editMode, readOnly, firNumber]);

  // Enable/disable marker dragging when edit mode changes
  useEffect(() => {
    if (!markerRef.current) return;
    if (editMode) {
      markerRef.current.dragging?.enable();
    } else {
      markerRef.current.dragging?.disable();
    }
  }, [editMode]);

  // ── Geocode with custom address ──────────────────────────────────────────
  const handleReocode = async () => {
    if (!editAddress.trim()) return;
    try {
      setGeocoding(true);
      setError(null);
      const res = await api.post(`/cases/${caseId}/location/geocode`, {
        custom_address: editAddress.trim(),
      });
      setLocationData(res.data);
      setDraftLat(null);
      setDraftLng(null);
      setSuccessMsg('Location re-geocoded successfully.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Geocoding failed.');
    } finally {
      setGeocoding(false);
    }
  };

  // ── Save / verify location ───────────────────────────────────────────────
  const handleSaveConfirmed = async () => {
    try {
      setSaving(true);
      setError(null);
      const payload: any = {
        incident_location_verified: true,
        incident_location_geocoder_status: 'MANUAL_CONFIRMED',
      };
      if (draftLat !== null) payload.incident_latitude = draftLat;
      if (draftLng !== null) payload.incident_longitude = draftLng;
      if (editAddress.trim()) payload.incident_location_normalized = editAddress.trim();

      const res = await api.put(`/cases/${caseId}/location`, payload);
      setLocationData(res.data);
      setEditMode(false);
      setDraftLat(null);
      setDraftLng(null);
      setEditAddress('');
      setSuccessMsg('Location confirmed and saved. Audit trail updated.');
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to save location.');
    } finally {
      setSaving(false);
    }
  };

  // ── Verify without editing ───────────────────────────────────────────────
  const handleVerify = async () => {
    try {
      setSaving(true);
      setError(null);
      const res = await api.put(`/cases/${caseId}/location`, {
        incident_location_verified: true,
        incident_location_geocoder_status: 'MANUAL_CONFIRMED',
      });
      setLocationData(res.data);
      setSuccessMsg('Location verified and audit trail updated.');
      setTimeout(() => setSuccessMsg(null), 3500);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Verification failed.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-3 p-6 text-slate-500 text-xs">
        <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
        Loading incident location…
      </div>
    );
  }

  const hasCoords =
    locationData?.incident_latitude != null && locationData?.incident_longitude != null;
  const isVerified = locationData?.incident_location_verified;
  const geocoderStatus = locationData?.incident_location_geocoder_status || 'UNRESOLVED';
  const isApproximate =
    geocoderStatus === 'APPROXIMATE' || locationData?.is_approximate;
  const directionsUrl = locationData?.directions_url;

  return (
    <div className="space-y-4">
      {/* ── Status bar ── */}
      <div className="flex flex-wrap items-center gap-2">
        <MapPin className="w-4 h-4 text-blue-600 flex-shrink-0" />
        <span className="font-bold text-sm text-slate-800">Incident Location &amp; Navigation</span>
        {statusBadge(geocoderStatus)}
        {isVerified && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-200">
            <CheckCircle2 className="w-3 h-3" /> Officer Verified
          </span>
        )}
        {isApproximate && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-3 h-3" /> ⚠ Approximate — verify before use
          </span>
        )}
      </div>

      {/* ── Alerts ── */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          <button onClick={() => setError(null)} className="ml-auto">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}
      {successMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> {successMsg}
        </div>
      )}

      {/* ── Location metadata grid ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-xs">
        <div>
          <span className="text-slate-400 block text-[11px]">Raw FIR Text</span>
          <span className="font-medium text-slate-800 leading-snug">
            {locationData?.incident_place_raw || '—'}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Normalized Address</span>
          <span className="font-medium text-slate-800">
            {locationData?.incident_location_normalized || '—'}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Village / Locality</span>
          <span className="font-medium text-slate-800">{locationData?.incident_village || '—'}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Mandal</span>
          <span className="font-medium text-slate-800">{locationData?.incident_mandal || '—'}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">District</span>
          <span className="font-medium text-slate-800">{locationData?.incident_district || '—'}</span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Coordinates</span>
          <span className="font-mono text-slate-700">
            {hasCoords
              ? `${locationData!.incident_latitude!.toFixed(5)}, ${locationData!.incident_longitude!.toFixed(5)}`
              : 'Not resolved'}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block text-[11px]">Confidence</span>
          <span className="font-medium text-slate-800">
            {locationData?.incident_location_confidence != null
              ? `${(locationData.incident_location_confidence * 100).toFixed(0)}%`
              : '—'}
          </span>
        </div>
        {locationData?.incident_location_verified_by && (
          <div>
            <span className="text-slate-400 block text-[11px]">Verified By</span>
            <span className="font-medium text-slate-800">
              {locationData.incident_location_verified_by}
            </span>
          </div>
        )}
      </div>

      {/* ── Action buttons ── */}
      <div className="flex flex-wrap gap-2">
        {directionsUrl && (
          <a
            href={directionsUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-sm"
          >
            <Navigation className="w-3.5 h-3.5" />
            Get Directions
            <ExternalLink className="w-3 h-3" />
          </a>
        )}

        {!readOnly && !isVerified && hasCoords && (
          <button
            onClick={handleVerify}
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-sm disabled:opacity-60"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            {saving ? 'Verifying…' : 'Verify Location'}
          </button>
        )}

        {!readOnly && !editMode && (
          <button
            onClick={() => {
              setEditMode(true);
              setEditAddress(locationData?.incident_location_normalized || locationData?.incident_place_raw || '');
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-semibold shadow-sm"
          >
            <Edit2 className="w-3.5 h-3.5" />
            Edit Location
          </button>
        )}

        {editMode && (
          <button
            onClick={() => { setEditMode(false); setDraftLat(null); setDraftLng(null); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-semibold"
          >
            <X className="w-3.5 h-3.5" />
            Cancel
          </button>
        )}

        <button
          onClick={fetchLocation}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-semibold"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>

        {locationData?.incident_location_evidence_passage && (
          <button
            onClick={() => setShowSource(!showSource)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-semibold"
          >
            <FileText className="w-3.5 h-3.5" />
            {showSource ? 'Hide Source' : 'View Source in FIR'}
          </button>
        )}
      </div>

      {/* ── Edit panel ── */}
      {editMode && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-3">
          <p className="text-xs font-semibold text-amber-800">
            Edit location address and re-geocode, or drag the marker on the map to set coordinates manually.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={editAddress}
              onChange={(e) => setEditAddress(e.target.value)}
              placeholder="Enter corrected address, village, mandal or landmark…"
              className="flex-1 border border-slate-300 rounded-lg px-3 py-1.5 text-xs bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
            <button
              onClick={handleReocode}
              disabled={geocoding || !editAddress.trim()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold disabled:opacity-60"
            >
              {geocoding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
              {geocoding ? 'Geocoding…' : 'Re-Geocode'}
            </button>
          </div>
          {draftLat !== null && (
            <p className="text-[11px] text-amber-700">
              Dragged to: {draftLat.toFixed(5)}, {draftLng?.toFixed(5)} — click "Save Confirmed Location" to persist.
            </p>
          )}
          <button
            onClick={handleSaveConfirmed}
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold shadow disabled:opacity-60"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save Confirmed Location'}
          </button>
        </div>
      )}

      {/* ── FIR source passage ── */}
      {showSource && locationData?.incident_location_evidence_passage && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs space-y-1">
          <p className="font-semibold text-slate-700 text-[11px] uppercase tracking-wide">
            Original FIR passage (page {locationData.incident_location_source_page || '?'})
          </p>
          <p className="text-slate-700 leading-relaxed italic">
            "{locationData.incident_location_evidence_passage}"
          </p>
        </div>
      )}

      {/* ── Map ── */}
      <div className="rounded-xl overflow-hidden border border-slate-200 shadow-sm">
        {!hasCoords && !loading && (
          <div className="flex items-center justify-center gap-2 bg-slate-100 text-slate-500 text-xs p-3 border-b border-slate-200">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Coordinates not yet resolved — showing Andhra Pradesh overview. Use Edit Location to set a precise point.
          </div>
        )}
        <div ref={mapRef} style={{ height: '360px', width: '100%' }} />
      </div>
    </div>
  );
};
