import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, MapPin, RefreshCw, Filter, X } from 'lucide-react';
import api from '../../api/client';
import { HotspotCluster, HotspotIncident, HotspotMap, INTENSITY_COLOUR } from './HotspotMap';

interface HotspotResponse {
  hotspots: HotspotCluster[];
  total_hotspots: number;
  incidents: HotspotIncident[];
  unlocated_cases: (Omit<HotspotIncident, 'latitude' | 'longitude'> & { location_text?: string })[];
  totals: { cases: number; located: number; unlocated: number };
  filters: { offence_types: string[]; contraband_types: string[] };
  levels: Record<string, string>;
  disclaimer: string;
}

const BADGE: Record<string, string> = {
  HIGH: 'bg-red-100 text-red-800',
  MEDIUM: 'bg-amber-100 text-amber-800',
  LOW: 'bg-emerald-100 text-emerald-800',
};

const units = (byUnit: Record<string, number>) =>
  Object.entries(byUnit).map(([u, q]) => (u === 'INR' ? `₹${q.toLocaleString('en-IN')}` : `${q} ${u}`)).join(' · ') || '—';

export const HotspotsTab: React.FC = () => {
  const [data, setData] = useState<HotspotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ date_from: '', date_to: '', offence_type: '', contraband_type: '' });
  const [selected, setSelected] = useState<HotspotCluster | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
      const res = await api.get('/analytics/hotspots', { params, timeout: 30000 });
      setData(res.data);
      setSelected(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : e?.message || 'Hotspots could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key: keyof typeof filters, value: string) => setFilters((f) => ({ ...f, [key]: value }));
  const anyFilter = Object.values(filters).some(Boolean);
  const onSelect = useCallback((c: HotspotCluster) => setSelected(c), []);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
          <div>
            <h3 className="font-bold text-sm text-slate-800">Geospatial Incident Hotspots &amp; Clusters</h3>
            <p className="text-xs text-slate-500">
              Each case's incident location, clustered by station / mandal and distance, within your jurisdiction.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="px-2 py-1 rounded bg-red-100 text-red-800 font-bold text-[11px]">High (5+ cases or 50L+)</span>
            <span className="px-2 py-1 rounded bg-amber-100 text-amber-800 font-bold text-[11px]">Medium (2+ cases)</span>
            <span className="px-2 py-1 rounded bg-emerald-100 text-emerald-800 font-bold text-[11px]">Low (1 case)</span>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-2 text-xs">
          <Filter className="w-4 h-4 text-slate-400 mb-2" />
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-500">From</span>
            <input type="date" value={filters.date_from} onChange={(e) => setFilter('date_from', e.target.value)}
              className="border border-slate-200 rounded px-2 py-1" />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-500">To</span>
            <input type="date" value={filters.date_to} onChange={(e) => setFilter('date_to', e.target.value)}
              className="border border-slate-200 rounded px-2 py-1" />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-500">Offence type</span>
            <select value={filters.offence_type} onChange={(e) => setFilter('offence_type', e.target.value)}
              className="border border-slate-200 rounded px-2 py-1 max-w-[220px]">
              <option value="">All</option>
              {data?.filters.offence_types.map((o) => <option key={o} value={o}>{o.length > 60 ? o.slice(0, 60) + '…' : o}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-500">Contraband type</span>
            <select value={filters.contraband_type} onChange={(e) => setFilter('contraband_type', e.target.value)}
              className="border border-slate-200 rounded px-2 py-1 max-w-[200px]">
              <option value="">All</option>
              {data?.filters.contraband_types.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          {anyFilter && (
            <button onClick={() => setFilters({ date_from: '', date_to: '', offence_type: '', contraband_type: '' })}
              className="flex items-center gap-1 px-2 py-1 border border-slate-200 rounded text-slate-600 hover:bg-slate-50">
              <X className="w-3 h-3" /> Clear filters
            </button>
          )}
          {data && (
            <span className="ml-auto text-slate-500">
              {data.total_hotspots} hotspot(s) · {data.totals.located} located case(s) · {data.totals.unlocated} not yet located
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-4 text-xs flex items-center justify-between gap-3" role="alert">
          <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{error}</span>
          <button onClick={load} className="flex items-center gap-1 px-3 py-1.5 bg-white border border-red-200 rounded-md font-semibold hover:bg-red-100">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center gap-2 text-xs text-slate-500 p-4"><RefreshCw className="w-4 h-4 animate-spin" /> Loading hotspots…</div>
      )}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 relative">
            <HotspotMap clusters={data.hotspots} incidents={data.incidents} selectedId={selected?.cluster_id} onSelect={onSelect} />
            {loading && <div className="absolute inset-0 bg-white/50 flex items-center justify-center text-xs"><RefreshCw className="w-4 h-4 animate-spin" /></div>}
            {data.total_hotspots === 0 && !loading && (
              <p className="mt-2 text-xs text-slate-500">No located cases match these filters.</p>
            )}
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-3 text-xs space-y-2 max-h-[420px] overflow-y-auto">
            {selected ? (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="font-bold text-slate-900 text-sm">{selected.location_name}</h4>
                    <span className="text-slate-500">{selected.station}, {selected.district}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${BADGE[selected.risk_intensity]}`}>{selected.risk_intensity}</span>
                </div>
                <p className="text-slate-600">{selected.incident_count} case(s) · Seized: {units(selected.seized_by_unit)}</p>
                <ul className="divide-y divide-slate-100">
                  {selected.cases.map((c) => (
                    <li key={c.case_id} className="py-1.5">
                      <Link to={`/cases/${c.case_id}`} className="font-semibold text-blue-700 hover:underline">{c.fir_number}</Link>
                      {c.status === 'DRAFT' && <span className="ml-1 text-[10px] text-slate-400">(draft)</span>}
                      <span className="block text-slate-500">
                        {c.incident_date?.slice(0, 10) || 'date not recorded'} · {c.contraband_type || 'contraband not recorded'}
                        {c.seized_quantity ? ` · ${c.seized_quantity} ${c.seized_unit || ''}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
                <button onClick={() => setSelected(null)} className="text-blue-700 hover:underline">Show all hotspots</button>
              </>
            ) : (
              <>
                <p className="font-bold text-slate-700">Hotspots (click one, or a circle on the map)</p>
                {data.hotspots.map((h) => (
                  <button key={h.cluster_id} onClick={() => setSelected(h)}
                    className="w-full text-left p-2 rounded-lg border border-slate-100 hover:bg-slate-50 flex items-center gap-2">
                    <MapPin className="w-4 h-4 shrink-0" style={{ color: INTENSITY_COLOUR[h.risk_intensity] }} />
                    <span className="flex-1">
                      <span className="font-semibold text-slate-800">{h.location_name}</span>
                      <span className="block text-slate-500">{h.station}, {h.district} · {h.incident_count} case(s) · {units(h.seized_by_unit)}</span>
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${BADGE[h.risk_intensity]}`}>{h.risk_intensity}</span>
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      )}

      {data && data.unlocated_cases.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs space-y-2">
          <p className="font-bold text-amber-900 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" /> Location not yet verified ({data.unlocated_cases.length})
          </p>
          <p className="text-amber-800">These cases have no geocoded incident location, so they are not on the map. Open a case to confirm its location.</p>
          <ul className="grid sm:grid-cols-2 gap-1">
            {data.unlocated_cases.map((c) => (
              <li key={c.case_id}>
                <Link to={`/cases/${c.case_id}`} className="font-semibold text-blue-700 hover:underline">{c.fir_number}</Link>
                <span className="text-amber-900"> · {c.station}, {c.district}{c.location_text ? ` · “${c.location_text.slice(0, 60)}”` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data && <p className="text-[11px] text-slate-400">{data.disclaimer}</p>}
    </div>
  );
};
