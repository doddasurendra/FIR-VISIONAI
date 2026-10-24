import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  Search,
  Filter,
  Plus,
  ChevronRight,
  ShieldAlert,
  FileText,
  Clock,
  CheckCircle,
  Edit2,
  Eye,
  X,
  FolderOpen,
  ArrowLeft
} from 'lucide-react';
import { FIRFormSelectionModal } from '../components/FIRFormSelectionModal';
import { DateWiseFIRSearch } from '../components/DateWiseFIRSearch';

export const CaseManagement: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Read initial filter from URL search params
  const statusParam = searchParams.get('status') || '';
  const searchParam = searchParams.get('search') || searchParams.get('q') || '';

  const [cases, setCases] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(searchParam);
  const [statusFilter, setStatusFilter] = useState(statusParam);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [showFormModal, setShowFormModal] = useState(false);

  // Sync state when URL search params change (browser Back / Forward navigation)
  useEffect(() => {
    const currentStatus = searchParams.get('status') || '';
    const currentSearch = searchParams.get('search') || searchParams.get('q') || '';
    setStatusFilter(currentStatus);
    setSearch(currentSearch);
  }, [searchParams]);

  const fetchCases = async () => {
    try {
      setLoading(true);
      const params: any = { limit: 100 };
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/cases/', { params });
      setCases(res.data);
      const headerTotal = res.headers['x-total-count'];
      setTotalCount(headerTotal ? parseInt(headerTotal, 10) : res.data.length);
    } catch (e) {
      console.error('Failed to load cases:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, [statusFilter, user]);

  const handleStatusChange = (newStatus: string) => {
    setStatusFilter(newStatus);
    const newParams: Record<string, string> = {};
    if (newStatus) newParams.status = newStatus;
    if (search.trim()) newParams.search = search.trim();
    setSearchParams(newParams);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newParams: Record<string, string> = {};
    if (statusFilter) newParams.status = statusFilter;
    if (search.trim()) newParams.search = search.trim();
    setSearchParams(newParams);
    fetchCases();
  };

  const clearStatusFilter = () => {
    handleStatusChange('');
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link
              to="/"
              className="inline-flex items-center text-xs text-slate-500 hover:text-slate-800 transition-colors mr-1"
              title="Return to Dashboard"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" />
              Dashboard
            </Link>
            <span className="text-slate-300">/</span>
            <h2 className="text-lg font-bold text-slate-800">{t.nav.caseManagement}</h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Database of authorized First Information Reports under your jurisdiction scope
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowFormModal(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>{t.nav.newCaseIntake}</span>
        </button>
      </div>

      {/* Filter Quick Pills */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => handleStatusChange('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
            statusFilter === ''
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          <FolderOpen className="w-3.5 h-3.5" />
          <span>All Cases</span>
        </button>

        <button
          type="button"
          onClick={() => handleStatusChange('IN_REVIEW')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
            statusFilter === 'IN_REVIEW'
              ? 'bg-amber-600 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Clock className="w-3.5 h-3.5 text-amber-500" />
          <span>Under Review</span>
        </button>

        <button
          type="button"
          onClick={() => handleStatusChange('APPROVED')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
            statusFilter === 'APPROVED'
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
          <span>Approved FIRs</span>
        </button>

        <button
          type="button"
          onClick={() => handleStatusChange('DRAFT')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
            statusFilter === 'DRAFT'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Edit2 className="w-3.5 h-3.5 text-indigo-500" />
          <span>Pending Drafts</span>
        </button>

        <button
          type="button"
          onClick={() => handleStatusChange('ARCHIVED')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
            statusFilter === 'ARCHIVED'
              ? 'bg-slate-700 text-white shadow-sm'
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          <span>Archived</span>
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3">
        <form onSubmit={handleSearchSubmit} className="flex-1 flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search by FIR Number, Contraband, Offence, Vehicle..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-slate-800 text-white text-xs font-medium rounded-lg hover:bg-slate-700 cursor-pointer"
          >
            {t.common.search}
          </button>
        </form>

        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-slate-400 ml-1" />
          <select
            value={statusFilter}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
          >
            <option value="">All Case Statuses</option>
            <option value="DRAFT">DRAFT</option>
            <option value="IN_REVIEW">IN_REVIEW</option>
            <option value="APPROVED">APPROVED</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </select>
        </div>
      </div>

      {/* Active Filter Scope Banner */}
      {statusFilter && (
        <div className={`p-4 rounded-xl border flex items-center justify-between text-xs ${
          statusFilter === 'IN_REVIEW'
            ? 'bg-amber-50 border-amber-200 text-amber-900'
            : statusFilter === 'APPROVED'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : statusFilter === 'DRAFT'
            ? 'bg-indigo-50 border-indigo-200 text-indigo-900'
            : 'bg-slate-50 border-slate-200 text-slate-800'
        }`}>
          <div className="flex items-center gap-2.5">
            {statusFilter === 'IN_REVIEW' && <Clock className="w-4 h-4 text-amber-600 flex-shrink-0" />}
            {statusFilter === 'APPROVED' && <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />}
            {statusFilter === 'DRAFT' && <Edit2 className="w-4 h-4 text-indigo-600 flex-shrink-0" />}
            <div>
              <span className="font-bold">
                {statusFilter === 'IN_REVIEW' && 'Under Review Queue — Cases awaiting officer verification and sign-off'}
                {statusFilter === 'APPROVED' && 'Approved Cases — Formally verified FIR records ready for court filing'}
                {statusFilter === 'DRAFT' && 'Pending Drafts — Saved FIR drafts awaiting completion & submission'}
                {statusFilter === 'ARCHIVED' && 'Archived Cases — Soft-deleted or inactive case files'}
              </span>
              <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold bg-white/80 border border-current">
                {cases.length} record{cases.length !== 1 ? 's' : ''}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={clearStatusFilter}
            className="inline-flex items-center gap-1 font-semibold hover:underline cursor-pointer"
          >
            <span>Show all</span>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Cases Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="text-xs font-semibold text-slate-600">
            {statusFilter ? `${statusFilter} Records` : 'All Authorized FIR Records'}
            <span className="ml-2 font-normal text-slate-400">
              (Displaying {cases.length}{totalCount > cases.length ? ` of ${totalCount}` : ''} cases)
            </span>
          </div>
          {statusFilter === 'DRAFT' && (
            <button
              type="button"
              onClick={() => setShowFormModal(true)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Resume or Start New Draft</span>
            </button>
          )}
        </div>

        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-xs text-slate-500 mt-2">Loading authorized case records...</p>
          </div>
        ) : cases.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <FileText className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-semibold text-slate-700">No cases found in this scope</p>
            <p className="text-xs text-slate-400 mt-0.5">Try adjusting your filters or search query.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200 font-semibold tracking-wider text-[11px]">
                  <th className="px-5 py-3">FIR Number</th>
                  <th className="px-5 py-3">Jurisdiction</th>
                  <th className="px-5 py-3">Offence Nature</th>
                  <th className="px-5 py-3">Contraband Seized</th>
                  <th className="px-5 py-3">Vehicle Details</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {cases.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-5 py-3.5 font-bold text-blue-700 font-mono">
                      {c.fir_number}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="font-medium text-slate-800">{c.station}</div>
                      <div className="text-[11px] text-slate-400">{c.district} District</div>
                    </td>
                    <td className="px-5 py-3.5 max-w-xs truncate" title={c.offence_nature}>
                      {c.offence_nature}
                    </td>
                    <td className="px-5 py-3.5 font-medium">
                      {c.contraband_type ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="text-slate-900">{c.contraband_type}</span>
                          <span className="text-slate-500 text-[11px]">({c.seized_quantity} {c.seized_unit})</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">None reported</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 font-mono text-[11px]">
                      {c.vehicle_details || '—'}
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${
                          c.status === 'APPROVED'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : c.status === 'IN_REVIEW'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : c.status === 'ARCHIVED'
                            ? 'bg-slate-100 text-slate-600 border-slate-200'
                            : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        to={`/cases/${c.id}`}
                        className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded transition-colors ${
                          c.status === 'DRAFT'
                            ? 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100'
                            : c.status === 'IN_REVIEW'
                            ? 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                            : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
                        }`}
                      >
                        {c.status === 'DRAFT' ? (
                          <>
                            <Edit2 className="w-3 h-3" />
                            <span>Continue Draft</span>
                          </>
                        ) : c.status === 'IN_REVIEW' ? (
                          <>
                            <Eye className="w-3 h-3" />
                            <span>Review Case</span>
                          </>
                        ) : (
                          <>
                            <Eye className="w-3 h-3" />
                            <span>Details</span>
                          </>
                        )}
                        <ChevronRight className="w-3.5 h-3.5" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Date-Wise FIR Search and Filtering Section */}
      <DateWiseFIRSearch />

      {/* Multilingual FIR Application Form Selection Modal */}
      {showFormModal && (
        <FIRFormSelectionModal onClose={() => setShowFormModal(false)} />
      )}
    </div>
  );
};
