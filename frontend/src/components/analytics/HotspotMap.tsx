import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { escapeHtml } from '../common/escapeHtml';

export interface HotspotIncident {
  case_id: string;
  fir_number: string;
  station?: string;
  district?: string;
  contraband_type?: string;
  offence_nature?: string;
  seized_quantity?: number | null;
  seized_unit?: string | null;
  incident_date?: string | null;
  status?: string;
  geocoder_status?: string | null;
  /** Same rule as the case page: VERIFIED, EXACT, APPROXIMATE or NONE */
  location_precision?: string;
  is_approximate?: boolean;
  latitude: number;
  longitude: number;
}

export interface HotspotCluster {
  cluster_id: string;
  location_name: string;
  station: string;
  district: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  incident_count: number;
  risk_intensity: 'HIGH' | 'MEDIUM' | 'LOW';
  seized_by_unit: Record<string, number>;
  contraband_breakdown: Record<string, number>;
  cases: HotspotIncident[];
}

export const INTENSITY_COLOUR: Record<string, string> = { HIGH: '#dc2626', MEDIUM: '#d97706', LOW: '#059669' };

interface Props {
  clusters: HotspotCluster[];
  incidents: HotspotIncident[];
  selectedId?: string | null;
  onSelect: (cluster: HotspotCluster) => void;
}

/** Every incident as a dot, plus one circle per cluster coloured by intensity. Clicking a circle selects it. */
export const HotspotMap: React.FC<Props> = ({ clusters, incidents, selectedId, onSelect }) => {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!el.current || map.current) return;
    map.current = L.map(el.current, { zoomControl: true }).setView([15.9, 79.7], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18,
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    // Tiles are laid out for the container's size at creation; redo it when the tab/layout changes size
    const observer = new ResizeObserver(() => map.current?.invalidateSize());
    observer.observe(el.current);
    return () => {
      observer.disconnect();
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    const g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const bounds: L.LatLngExpression[] = [];
    clusters.forEach((c) => {
      const colour = INTENSITY_COLOUR[c.risk_intensity];
      // Sized on screen by case count, so a cluster stays visible at state-wide zoom
      const circle = L.circleMarker([c.latitude, c.longitude], {
        radius: 9 + 4 * Math.sqrt(c.incident_count),
        color: colour,
        weight: c.cluster_id === selectedId ? 4 : 2,
        fillColor: colour,
        fillOpacity: c.cluster_id === selectedId ? 0.5 : 0.3,
      });
      circle.bindTooltip(escapeHtml(`${c.location_name} · ${c.incident_count} case(s) · ${c.risk_intensity}`));
      circle.on('click', () => onSelect(c));
      circle.addTo(g);
      bounds.push([c.latitude, c.longitude]);
    });
    incidents.forEach((i) => {
      // Approximate points (area match or mandal/district centroid): hollow, dashed, and labelled
      const approx = i.is_approximate ?? !['EXACT', 'MANUAL_CONFIRMED'].includes(i.geocoder_status || '');
      L.circleMarker([i.latitude, i.longitude], approx
        ? { radius: 5, color: '#b45309', weight: 2, dashArray: '3 2', fillColor: '#fde68a', fillOpacity: 0.6 }
        : { radius: 4, color: '#1e3a8a', weight: 1, fillColor: '#3b82f6', fillOpacity: 0.9 })
        .bindTooltip(escapeHtml(`${i.fir_number}${i.contraband_type ? ' · ' + i.contraband_type : ''}${approx ? ' · approximate location' : ''}`))
        .addTo(g);
    });
    m.invalidateSize();
    if (bounds.length) m.fitBounds(L.latLngBounds(bounds), { padding: [40, 40], maxZoom: 13 });
    // Once the surrounding layout has settled, lay the tiles out again
    const t = window.setTimeout(() => m.invalidateSize(), 250);
    return () => window.clearTimeout(t);
  }, [clusters, incidents, selectedId, onSelect]);

  return <div ref={el} className="w-full h-[420px] rounded-xl border border-slate-200 z-0" data-testid="hotspot-map" />;
};
