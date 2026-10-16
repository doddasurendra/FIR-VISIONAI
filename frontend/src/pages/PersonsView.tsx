import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Users, User, Search, AlertCircle, RefreshCw, ChevronRight,
  Home, ExternalLink, Shield, AlertTriangle
} from 'lucide-react';
import api from '../api/client';

interface PersonRecord {
  id: string;
  canonical_name: string;
  aliases: string[];
  risk_score: number;
  verification_status: string;
  case_count: number;
  attributes: Record<string, string>;
}

interface PersonsResponse {
  persons: PersonRecord[];
  total: number;
}

export const PersonsView: React.FC = () => {
  const { type } = useParams<{ type: string }>(); // 'single-fir' | 'multiple-fir'
  const navigate = useNavigate();
  const isMulti = type === 'multiple-fir';

  const [data, setData] = useState<PersonsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const limit = 50;

  const fetchPersons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = isMulti ? '/folders/persons/multiple-fir' : '/folders/persons/single-fir';
      const params: Record<string, string | number> = { skip: page * limit, limit };
      if (search) params.search = search;
      const res = await api.get<PersonsResponse>(endpoint, { params });
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load person records.');
    } finally {
      setLoading(false);
    }
  }, [isMulti, page, search]);

  useEffect(() => { fetchPersons(); }, [fetchPersons]);

  const totalPages = data ? Math.ceil(data.total / limit) : 0;
  const title = isMulti ? 'Multiple-FIR Person Records' : 'Single-FIR Persons';
  const subtitle = isMulti
    ? 'Persons appearing in 2 or more FIRs within your authorized jurisdiction.'
    : 'Persons appearing in exactly one FIR within your authorized jurisdiction.';

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    fetchPersons();
  };

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
        <span className="text-slate-800 font-semibold">{title}</span>
      </nav>

      {/* Header */}
      <div className="flex items-center space-x-3 p-4 bg-white rounded-lg border border-slate-200 shadow-sm">
        <div className={`p-2.5 rounded-lg ${isMulti ? 'bg-red-50' : 'bg-blue-50'}`}>
          {isMulti ? (
            <Users className="w-6 h-6 text-red-600" />
          ) : (
            <User className="w-6 h-6 text-blue-600" />
          )}
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-500">{subtitle}</p>
        </div>
        <div className="ml-auto">
          <span className="text-sm font-semibold text-slate-600">
            {data?.total ?? '…'} record{data?.total !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Privacy notice for multi-FIR */}
      {isMulti && (
        <div className="flex items-start space-x-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>
            <strong>Access Notice:</strong> This view shows person records extracted from FIR documents within your authorized jurisdiction.
            Information is advisory only. All records must be independently verified before any official action.
          </span>
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search person name…"
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

      {/* Error */}
      {error && (
        <div className="flex items-center space-x-3 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={fetchPersons} className="ml-auto flex items-center space-x-1 hover:underline">
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

      {/* Table */}
      {!loading && !error && data && (
        <>
          {data.persons.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <Users className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p className="font-semibold text-slate-600">No person records found</p>
              <p className="text-sm mt-1">Person records are extracted automatically from uploaded FIR documents.</p>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Name</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Aliases</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">FIR Count</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Verification</th>
                      <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">Risk Score</th>
                      <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wide">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.persons.map(p => (
                      <tr key={p.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-3 font-semibold text-slate-900">{p.canonical_name}</td>
                        <td className="px-4 py-3 text-slate-500 text-xs">
                          {p.aliases.length > 0 ? p.aliases.join(', ') : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${
                            p.case_count >= 3 ? 'bg-red-100 text-red-800' :
                            p.case_count >= 2 ? 'bg-amber-100 text-amber-800' :
                            'bg-blue-100 text-blue-800'
                          }`}>
                            {p.case_count} FIR{p.case_count !== 1 ? 's' : ''}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                            p.verification_status === 'CONFIRMED' ? 'bg-green-100 text-green-800' :
                            p.verification_status === 'REVIEW_PENDING' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-slate-100 text-slate-600'
                          }`}>
                            {p.verification_status === 'CONFIRMED' && <Shield className="w-3 h-3" />}
                            <span>{p.verification_status.replace('_', ' ')}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center space-x-2">
                            <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  p.risk_score >= 0.7 ? 'bg-red-500' :
                                  p.risk_score >= 0.4 ? 'bg-amber-500' : 'bg-green-500'
                                }`}
                                style={{ width: `${Math.min(100, Math.round(p.risk_score * 100))}%` }}
                              />
                            </div>
                            <span className="text-xs text-slate-500">{Math.round(p.risk_score * 100)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => navigate(`/network`)}
                            className="inline-flex items-center space-x-1 text-xs font-semibold text-[#0f5132] hover:underline"
                          >
                            <span>View Network</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

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
    </div>
  );
};

export default PersonsView;
