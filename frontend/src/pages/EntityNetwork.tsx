import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { NetworkGraph } from '../components/network/NetworkGraph';
import {
  Share2,
  Users,
  Car,
  MapPin,
  Building,
  Info,
  ShieldAlert,
  Search
} from 'lucide-react';

export const EntityNetwork: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const queryEntityId = searchParams.get('entityId');
  const queryCaseId = searchParams.get('caseId');

  const [graphData, setGraphData] = useState<any>({ nodes: [], edges: [], communities: [] });
  const [loading, setLoading] = useState(true);
  const [selectedFilter, setSelectedFilter] = useState('ALL');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEntityProfile, setSelectedEntityProfile] = useState<any>(null);

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        setLoading(true);
        const res = await api.get('/entities/network-graph');
        setGraphData(res.data);

        // Auto-select node if specified in URL query
        if (queryEntityId && res.data.nodes?.some((n: any) => n.id === queryEntityId)) {
          handleNodeClick(queryEntityId);
        } else if (res.data.nodes?.length > 0 && !selectedNodeId) {
          handleNodeClick(res.data.nodes[0].id);
        }
      } catch (e) {
        console.error('Failed to load network graph:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchGraph();
  }, [user, queryEntityId, queryCaseId]);

  const handleNodeClick = async (nodeId: string) => {
    setSelectedNodeId(nodeId);
    try {
      const res = await api.get(`/entities/${nodeId}`);
      setSelectedEntityProfile(res.data);
    } catch (e) {
      console.error('Failed to fetch entity profile:', e);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Share2 className="w-5 h-5 text-blue-600" />
            <span>{t.nav.entityNetwork}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Co-occurrence Network & Louvain Community Detection (Analytical leads only — not confirmed criminal organizations)
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 bg-white p-1 rounded-lg border border-slate-200 text-xs shadow-2xs">
          {['ALL', 'PERSON', 'VEHICLE', 'LOCATION', 'ORGANIZATION'].map((ft) => (
            <button
              key={ft}
              onClick={() => setSelectedFilter(ft)}
              className={`px-3 py-1 rounded font-semibold transition-colors ${
                selectedFilter === ft
                  ? 'bg-blue-600 text-white shadow-2xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {ft}
            </button>
          ))}
        </div>
      </div>

      {/* Main Graph & Inspector Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[650px]">
        {/* Left: Interactive Vis-Network Canvas */}
        <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 shadow-sm relative overflow-hidden flex flex-col">
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : (
            <div className="flex-1 w-full h-full relative">
              <NetworkGraph
                nodes={graphData.nodes || []}
                edges={graphData.edges || []}
                onSelectNode={handleNodeClick}
                selectedFilter={selectedFilter}
              />
              {/* Legend Overlay */}
              <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur-sm p-3 rounded-lg border border-slate-200 shadow-md text-[11px] space-y-1.5 pointer-events-none">
                <span className="font-bold text-slate-700 block mb-1">Entity Types:</span>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block"></span>
                  <span>Person</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span>
                  <span>Vehicle / Conveyance</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
                  <span>Location</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block"></span>
                  <span>Organization</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Selected Node / Community Lead Inspector */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 overflow-y-auto flex flex-col text-xs space-y-4">
          <h3 className="font-bold text-sm text-slate-800 border-b border-slate-100 pb-2 flex items-center justify-between">
            <span>Entity Lead Inspector</span>
            {selectedEntityProfile && (
              <span className="text-[10px] bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded font-bold">
                {selectedEntityProfile.entity?.entity_type}
              </span>
            )}
          </h3>

          {selectedEntityProfile ? (
            <div className="space-y-4">
              <div>
                <span className="text-slate-400 block text-[11px]">Canonical Identity</span>
                <h4 className="font-bold text-base text-slate-900">{selectedEntityProfile.entity?.canonical_name}</h4>
              </div>

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-500">Risk Assessment:</span>
                  <span className="font-bold text-blue-700">{selectedEntityProfile.entity?.risk_score}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Status:</span>
                  <span className="font-semibold text-emerald-700">{selectedEntityProfile.entity?.verification_status}</span>
                </div>
              </div>

              <div>
                <h5 className="font-bold text-xs text-slate-800 mb-2">Linked Case Crime Records ({selectedEntityProfile.linked_cases?.length || 0}):</h5>
                <div className="space-y-2">
                  {selectedEntityProfile.linked_cases?.map((lc: any, idx: number) => (
                    <div key={idx} className="p-2.5 bg-slate-50 rounded border border-slate-200">
                      <span className="font-mono text-blue-700 font-bold block">{lc.case?.fir_number}</span>
                      <p className="text-[11px] text-slate-600 mt-0.5">{lc.case?.offence_nature}</p>
                      <span className="text-[10px] text-slate-400 block mt-1">Role: {lc.mention?.role_in_case}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center text-slate-400 p-4">
              <Info className="w-8 h-8 text-slate-300 mb-2" />
              <p className="font-medium text-slate-600">Click any node on the graph</p>
              <p className="text-[11px] text-slate-400 mt-1">
                Inspect cross-case connections, suspect conveyance ownership, and risk signals.
              </p>
            </div>
          )}

          {/* Communities List */}
          <div className="pt-3 border-t border-slate-100">
            <h4 className="font-bold text-xs text-slate-700 mb-2">Detected Louvain Communities:</h4>
            <div className="space-y-1.5">
              {graphData.communities?.map((comm: any, idx: number) => (
                <div key={idx} className="p-2 bg-slate-50 rounded flex items-center justify-between text-[11px]">
                  <span className="font-medium text-slate-700">{comm.label}</span>
                  <span className="font-mono bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded font-bold">
                    {comm.size} Nodes
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
