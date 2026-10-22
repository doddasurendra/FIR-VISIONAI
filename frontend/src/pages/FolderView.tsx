import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Folder, Search, Filter, ChevronRight, ExternalLink,
  Clock, AlertCircle, CheckCircle2, FileText, RefreshCw, Home
} from 'lucide-react';
import api from '../api/client';
import { DateWiseFIRSearch } from '../components/DateWiseFIRSearch';

interface FolderMeta {
  id: string;
  name: string;
  slug: string;
  description: string;
  color_code: string;
  icon_name: string;
}

interface CaseRow {
  id: string;
  fir_number: string;
  year: number;
  district: string;
  station: string;
  offence_nature: string;
  status: string;
  registration_date: string | null;
  classification_confidence: number | null;
  classification_status: string | null;
}

interface FolderCasesResponse {
  folder: FolderMeta;
  cases: CaseRow[];
  total: number;
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  DRAFT:     { label: 'Draft',     color: 'bg-yellow-100 text-yellow-800' },
  IN_REVIEW: { label: 'In Review', color: 'bg-blue-100 text-blue-800' },
  APPROVED:  { label: 'Approved',  color: 'bg-green-100 text-green-800' },
  ARCHIVED:  { label: 'Archived',  color: 'bg-slate-100 text-slate-600' },
};

export const FolderView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [data, setData] = useState<FolderCasesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const limit = 30;

  const fetchCases = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = { skip: page * limit, limit };
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      const res = await api.get<FolderCasesResponse>(`/folders/${slug}/cases`, { params });
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load folder cases.');
    } finally {
      setLoading(false);
    }
  }, [slug, page, search, statusFilter]);

  useEffect(() => { fetchCases(); }, [fetchCases]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    fetchCases();
  };

  const totalPages = data ? Math.ceil(data.total / limit) : 0;

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <nav className="flex items-center space-x-2 text-sm text-slate-500">
        <button onClick={() => navigate('/')} className="flex items-center hover:text-slate-800 transition-colors">
          <Home className="w-3.5 h-3.5 mr-1" />
          Dashboard
        </button>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-slate-400">All FIR Folders</span>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-slate-800 font-semibold">{data?.folder?.name || slug}</span>
      </nav>

      {/* Folder Header */}
      {data?.folder && (
        <div className="flex items-center space-x-3 p-4 bg-white rounded-lg border border-slate-200 shadow-sm">
          <div
            className="p-2.5 rounded-lg"
            style={{ backgroundColor: (data.folder.color_code || '#0f5132') + '20' }}
          >
            <Folder className="w-6 h-6" style={{ color: data.folder.color_code || '#0f5132' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">{data.folder.name}</h1>
            {data.folder.description && (
              <p className="text-sm text-slate-500">{data.folder.description}</p>
            )}
          </div>
          <div className="ml-auto">
            <span className="text-sm font-semibold text-slate-600">
              {data.total} case{data.total !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      )}

      {/* Search & Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <form onSubmit={handleSearch} className="flex flex-1 gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search FIR number, offence…"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#0f5132] focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-[#0f5132] text-white text-sm font-semibold rounded-md hover:bg-[#0a3d26] transition-colors"
          >
            Search
          </button>
        </form>
        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(0); }}
            className="text-sm border border-slate-300 rounded-md px-2 py-2 focus:outline-none focus:ring-2 focus:ring-[#0f5132]"
          >
            <option value="">All Statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="IN_REVIEW">In Review</option>
            <option value="APPROVED">Approved</option>
            <option value="ARCHIVED">Archived</option>
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center space-x-3 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={fetchCases} className="ml-auto flex items-center space-x-1 hover:underline">
            <RefreshCw className="w-3.5 h-3.5" /> <span>Retry</span>
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0f5132]"></div>
        </div>
      )}

      {/* Cases Table */}
      {!loading && !error && data && (
        <>
          {data.cases.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <Folder className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p className="font-semibold text-slate-600">No cases in this folder</p>
              <p className="text-sm mt-1">Cases are assigned automatically after document ingestion, or manually by officers.</p>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">FIR Number</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Offence</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">District / Station</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Registered</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">AI Confidence</th>
                      <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wide">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.cases.map(c => {
                      const statusInfo = STATUS_LABELS[c.status] || { label: c.status, color: 'bg-slate-100 text-slate-600' };
                      const confPct = c.classification_confidence != null
                        ? Math.round(c.classification_confidence * 100) + '%'
                        : '—';
                      return (
                        <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-3 font-mono font-semibold text-[#0f5132]">{c.fir_number}</td>
                          <td className="px-4 py-3 text-slate-700 max-w-[200px] truncate" title={c.offence_nature}>{c.offence_nature}</td>
                          <td className="px-4 py-3 text-slate-600">
                            <div>{c.district}</div>
                            <div className="text-xs text-slate-400">{c.station}</div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${statusInfo.color}`}>
                              {statusInfo.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-500 text-xs">
                            {c.registration_date ? new Date(c.registration_date).toLocaleDateString('en-IN') : '—'}
                          </td>
                          <td className="px-4 py-3 text-xs">
                            {c.classification_status === 'CLASSIFIED' ? (
                              <span className="flex items-center space-x-1 text-green-700">
                                <CheckCircle2 className="w-3 h-3" />
                                <span>{confPct}</span>
                              </span>
                            ) : c.classification_status === 'MANUAL_OVERRIDE' ? (
                              <span className="text-blue-700 font-semibold">Manual</span>
                            ) : (
                              <span className="flex items-center space-x-1 text-amber-600">
                                <Clock className="w-3 h-3" />
                                <span>Pending</span>
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => navigate(`/cases/${c.id}`)}
                              className="inline-flex items-center space-x-1 text-xs font-semibold text-[#0f5132] hover:underline"
                            >
                              <FileText className="w-3.5 h-3.5" />
                              <span>Open Case</span>
                              <ExternalLink className="w-3 h-3" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 text-sm text-slate-600">
                  <span>Showing {page * limit + 1}–{Math.min((page + 1) * limit, data.total)} of {data.total}</span>
                  <div className="flex space-x-2">
                    <button
                      disabled={page === 0}
                      onClick={() => setPage(p => p - 1)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
                    >Previous</button>
                    <button
                      disabled={page >= totalPages - 1}
                      onClick={() => setPage(p => p + 1)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
                    >Next</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Date-Wise FIR Search Section */}
      <div className="pt-4 border-t border-slate-200">
        <DateWiseFIRSearch />
      </div>
    </div>
  );
};

export default FolderView;
