import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  Search,
  Filter,
  Plus,
  ChevronRight,
  ShieldAlert,
  FileText
} from 'lucide-react';
import { FIRFormSelectionModal } from '../components/FIRFormSelectionModal';
import { DateWiseFIRSearch } from '../components/DateWiseFIRSearch';

export const CaseManagement: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [cases, setCases] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showFormModal, setShowFormModal] = useState(false);

  const fetchCases = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/cases/', { params });
      setCases(res.data);
    } catch (e) {
      console.error('Failed to load cases:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, [statusFilter, user]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchCases();
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800">{t.nav.caseManagement}</h2>
          <p className="text-xs text-slate-500">
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
            className="px-4 py-2 bg-slate-800 text-white text-xs font-medium rounded-lg hover:bg-slate-700"
          >
            {t.common.search}
          </button>
        </form>

        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-slate-400 ml-1" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Case Statuses</option>
            <option value="DRAFT">DRAFT</option>
            <option value="IN_REVIEW">IN_REVIEW</option>
            <option value="APPROVED">APPROVED</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </select>
        </div>
      </div>

      {/* Cases Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
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
                            : 'bg-blue-50 text-blue-700 border-blue-200'
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        to={`/cases/${c.id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800"
                      >
                        <span>Details</span>
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
