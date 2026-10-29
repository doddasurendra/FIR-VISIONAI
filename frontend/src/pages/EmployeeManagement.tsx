import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { LoadError, errorMessage } from '../components/common/LoadError';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  UserCheck,
  UserPlus,
  Shield,
  CheckCircle,
  XCircle,
  AlertCircle,
  Check,
  X,
  KeyRound,
  Clock,
  Building,
  MapPin,
  RefreshCw,
  Search,
  Filter
} from 'lucide-react';

export const EmployeeManagement: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<'directory' | 'pending'>('directory');
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Add Officer Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newEmp, setNewEmp] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'STATION',
    district: user?.district || 'Kurnool',
    station: 'Kurnool Town Station',
    badge_number: '',
    designation: 'Excise Sub-Inspector',
    department: 'AP Prohibition & Excise Department'
  });
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Reset Password Modal
  const [resetModalEmp, setResetModalEmp] = useState<any | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetSuccess, setResetSuccess] = useState<string | null>(null);

  // AP Master data for jurisdictions
  const [apDistricts, setApDistricts] = useState<string[]>([]);
  const [apStations, setApStations] = useState<string[]>([]);

  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchEmployees = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.get('/employees/');
      setEmployees(res.data);
    } catch (e) {
      console.error('Failed to load employees:', e);
      setLoadError(errorMessage(e, 'The officer list could not be loaded.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmployees();
  }, [user]);

  // Load AP Districts for Add Officer Modal
  useEffect(() => {
    const loadDistricts = async () => {
      try {
        const res = await api.get('/jurisdictions/districts');
        setApDistricts(res.data);
        // A state officer's own "district" is a headquarters, not a district: start on a real one
        setNewEmp((prev) => (res.data.includes(prev.district) || !res.data.length ? prev : { ...prev, district: res.data[0] }));
      } catch (e) {
        setApDistricts(['Kurnool', 'Guntur', 'Visakhapatnam', 'Chittoor', 'Krishna']);
      }
    };
    loadDistricts();
  }, []);

  // Load Stations when selected district changes (only for a known district)
  useEffect(() => {
    const loadStations = async () => {
      if (newEmp.district && apDistricts.includes(newEmp.district)) {
        try {
          const res = await api.get(`/jurisdictions/stations?district=${encodeURIComponent(newEmp.district)}`);
          setApStations(res.data);
          if (res.data.length > 0) {
            setNewEmp((prev) => ({ ...prev, station: res.data[0] }));
          }
        } catch (e) {
          setApStations([]);
        }
      }
    };
    loadStations();
  }, [newEmp.district, apDistricts]);

  const handleToggleStatus = async (id: string) => {
    try {
      await api.put(`/employees/${id}/toggle-status`);
      await fetchEmployees();
    } catch (e: any) {
      alert('Toggle error: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await api.post(`/employees/${id}/approve`);
      await fetchEmployees();
    } catch (e: any) {
      alert('Approval failed: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleReject = async (id: string) => {
    const reason = prompt('Please enter reason for rejecting registration:', 'Jurisdiction verification failed');
    if (reason === null) return;
    try {
      await api.post(`/employees/${id}/reject`, { decision: 'REJECT', reason });
      await fetchEmployees();
    } catch (e: any) {
      alert('Rejection failed: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetModalEmp || !newPassword) return;
    setResetLoading(true);
    try {
      await api.post(`/employees/${resetModalEmp.id}/reset-password`, {
        new_password: newPassword
      });
      setResetSuccess(`Password for officer '${resetModalEmp.username}' updated successfully.`);
      setTimeout(() => {
        setResetModalEmp(null);
        setNewPassword('');
        setResetSuccess(null);
      }, 1500);
    } catch (e: any) {
      alert('Password reset failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setResetLoading(false);
    }
  };

  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSubmitting(true);
      setErrorMsg(null);
      await api.post('/employees/', newEmp);
      setShowAddModal(false);
      setNewEmp({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: 'STATION',
        district: user?.district || 'Kurnool',
        station: 'Kurnool Town Station',
        badge_number: '',
        designation: 'Excise Sub-Inspector',
        department: 'AP Prohibition & Excise Department'
      });
      await fetchEmployees();
    } catch (e: any) {
      setErrorMsg(e.response?.data?.detail || 'Failed to create employee');
    } finally {
      setSubmitting(false);
    }
  };

  const pendingApprovals = employees.filter((e) => e.approval_status === 'PENDING_APPROVAL');
  const activeDirectory = employees.filter((e) => e.approval_status !== 'PENDING_APPROVAL');

  const filteredDirectory = activeDirectory.filter((e) => {
    const q = searchQuery.toLowerCase();
    return (
      e.full_name?.toLowerCase().includes(q) ||
      e.username?.toLowerCase().includes(q) ||
      e.district?.toLowerCase().includes(q) ||
      e.station?.toLowerCase().includes(q) ||
      e.badge_number?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <UserCheck className="w-5 h-5 text-blue-600" />
            <span>Administrative Account & Officer Governance</span>
          </h2>
          <p className="text-xs text-slate-500">
            Section 5: Registration Approvals, Role Scoping, Password Resets & Station Assignment
          </p>
        </div>

        {user?.role === 'STATE' || user?.role === 'DISTRICT' ? (
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            <span>Provision Officer</span>
          </button>
        ) : null}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-2 text-xs font-semibold">
        <button
          onClick={() => setActiveTab('directory')}
          className={`pb-3 px-4 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === 'directory'
              ? 'border-blue-600 text-blue-700 font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <span>Officer Directory ({activeDirectory.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('pending')}
          className={`pb-3 px-4 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === 'pending'
              ? 'border-blue-600 text-blue-700 font-bold'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Clock className="w-3.5 h-3.5 text-amber-500" />
          <span>Pending Registration Requests</span>
          {pendingApprovals.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500 text-white">
              {pendingApprovals.length}
            </span>
          )}
        </button>
      </div>

      {/* Search Bar for Directory */}
      {activeTab === 'directory' && (
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, username, district, or badge..."
              className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={fetchEmployees}
            className="p-2 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-lg text-xs flex items-center gap-1.5"
            title="Refresh List"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
      )}

      {/* TAB 1: OFFICER DIRECTORY */}
      {activeTab === 'directory' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : loadError ? (
            <div className="p-4">
              <LoadError message={loadError} onRetry={fetchEmployees} />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200 font-semibold text-[11px]">
                    <th className="px-5 py-3">Officer Name</th>
                    <th className="px-5 py-3">Role Scope</th>
                    <th className="px-5 py-3">Assigned Station / District</th>
                    <th className="px-5 py-3">Badge & Designation</th>
                    <th className="px-5 py-3">Account Status</th>
                    <th className="px-5 py-3 text-right">Administrative Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {filteredDirectory.map((emp) => (
                    <tr key={emp.id} className="hover:bg-slate-50/80">
                      <td className="px-5 py-3.5 font-medium">
                        <div className="font-bold text-slate-900">{emp.full_name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">@{emp.username} • {emp.email}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded border ${
                            emp.role === 'STATE'
                              ? 'bg-purple-100 text-purple-800 border-purple-200'
                              : emp.role === 'DISTRICT'
                              ? 'bg-indigo-100 text-indigo-800 border-indigo-200'
                              : 'bg-blue-100 text-blue-800 border-blue-200'
                          }`}
                        >
                          {emp.role}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="font-semibold text-slate-800">{emp.station || 'All District Stations'}</div>
                        <div className="text-[11px] text-slate-400">{emp.district}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div>{emp.designation || 'Excise Officer'}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{emp.badge_number || 'N/A'}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            emp.is_active
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-red-50 text-red-700 border-red-200'
                          }`}
                        >
                          {emp.is_active ? 'ACTIVE' : 'DEACTIVATED'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-right space-x-1.5">
                        <button
                          onClick={() => setResetModalEmp(emp)}
                          className="text-[11px] font-semibold px-2.5 py-1 rounded border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors inline-flex items-center gap-1"
                          title="Reset Password"
                        >
                          <KeyRound className="w-3 h-3 text-slate-500" />
                          <span>Reset Key</span>
                        </button>
                        <button
                          onClick={() => handleToggleStatus(emp.id)}
                          className={`text-[11px] font-semibold px-2.5 py-1 rounded border transition-colors ${
                            emp.is_active
                              ? 'text-red-700 border-red-200 hover:bg-red-50'
                              : 'text-emerald-700 border-emerald-200 hover:bg-emerald-50'
                          }`}
                        >
                          {emp.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: PENDING REGISTRATIONS */}
      {activeTab === 'pending' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {pendingApprovals.length === 0 ? (
            <div className="p-12 text-center text-slate-500 space-y-2">
              <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto" />
              <div className="font-semibold text-sm text-slate-700">No Pending Requests</div>
              <p className="text-xs text-slate-400">All self-registered officer accounts have been reviewed and approved.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-amber-50 text-amber-900 uppercase border-b border-amber-200 font-semibold text-[11px]">
                    <th className="px-5 py-3">Applicant Name</th>
                    <th className="px-5 py-3">Requested Role</th>
                    <th className="px-5 py-3">Requested Jurisdiction</th>
                    <th className="px-5 py-3">Badge & Designation</th>
                    <th className="px-5 py-3 text-right">Approval Decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {pendingApprovals.map((emp) => (
                    <tr key={emp.id} className="hover:bg-amber-50/40">
                      <td className="px-5 py-3.5 font-medium">
                        <div className="font-bold text-slate-900">{emp.full_name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">@{emp.username} • {emp.email}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300">
                          {emp.role} (PENDING)
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="font-semibold text-slate-800">{emp.station || 'District-Wide'}</div>
                        <div className="text-[11px] text-slate-500">{emp.district} District</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div>{emp.designation || 'Excise Officer'}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{emp.badge_number || 'N/A'}</div>
                      </td>
                      <td className="px-5 py-3.5 text-right space-x-2">
                        <button
                          onClick={() => handleApprove(emp.id)}
                          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md font-semibold text-xs inline-flex items-center gap-1 shadow-sm"
                        >
                          <Check className="w-3.5 h-3.5" />
                          <span>Approve & Activate</span>
                        </button>
                        <button
                          onClick={() => handleReject(emp.id)}
                          className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-md font-semibold text-xs inline-flex items-center gap-1 shadow-sm"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>Reject</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* MODAL: RESET PASSWORD */}
      {resetModalEmp && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 space-y-4 border border-slate-200">
            <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-blue-600" />
              <span>Reset Officer Password</span>
            </h3>
            <p className="text-xs text-slate-500">
              Set a new secure password for <strong className="text-slate-800">@{resetModalEmp.username}</strong> ({resetModalEmp.full_name}).
            </p>

            {resetSuccess && (
              <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg text-xs border border-emerald-200">
                {resetSuccess}
              </div>
            )}

            <form onSubmit={handleResetPassword} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">New Password (Min 6 chars)</label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new officer password"
                  className="w-full border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setResetModalEmp(null)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resetLoading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-500 shadow-sm disabled:opacity-50"
                >
                  {resetLoading ? 'Updating...' : 'Save New Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: PROVISION NEW OFFICER */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 space-y-4 border border-slate-200 max-h-[85vh] overflow-y-auto">
            <h3 className="font-bold text-base text-slate-900">Provision Operational Officer Account</h3>
            {errorMsg && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs flex items-center gap-1.5 border border-red-200">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}
            <form onSubmit={handleCreateEmployee} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Username *</label>
                  <input
                    type="text"
                    required
                    value={newEmp.username}
                    onChange={(e) => setNewEmp({ ...newEmp, username: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Email *</label>
                  <input
                    type="email"
                    required
                    value={newEmp.email}
                    onChange={(e) => setNewEmp({ ...newEmp, email: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Full Officer Name *</label>
                  <input
                    type="text"
                    required
                    value={newEmp.full_name}
                    onChange={(e) => setNewEmp({ ...newEmp, full_name: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Initial Password *</label>
                  <input
                    type="password"
                    required
                    value={newEmp.password}
                    onChange={(e) => setNewEmp({ ...newEmp, password: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
              </div>

              {/* Role Scope */}
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Role Jurisdiction Scope *</label>
                <select
                  value={newEmp.role}
                  onChange={(e) => setNewEmp({ ...newEmp, role: e.target.value })}
                  className="w-full border border-slate-300 rounded-lg p-2 bg-white"
                >
                  <option value="STATION">STATION (Station Only)</option>
                  <option value="DISTRICT">DISTRICT (District Wide)</option>
                  {user?.role === 'STATE' && <option value="STATE">STATE (All Districts)</option>}
                </select>
              </div>

              {/* AP Master Data Dropdowns */}
              {newEmp.role !== 'STATE' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Andhra Pradesh District *</label>
                    <select
                      value={newEmp.district}
                      onChange={(e) => setNewEmp({ ...newEmp, district: e.target.value })}
                      className="w-full border border-slate-300 rounded-lg p-2 bg-white"
                    >
                      {apDistricts.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                  {newEmp.role === 'STATION' && (
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Assigned Station *</label>
                      <select
                        value={newEmp.station}
                        onChange={(e) => setNewEmp({ ...newEmp, station: e.target.value })}
                        className="w-full border border-slate-300 rounded-lg p-2 bg-white"
                      >
                        {apStations.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Designation</label>
                  <select
                    value={newEmp.designation}
                    onChange={(e) => setNewEmp({ ...newEmp, designation: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2 bg-white"
                  >
                    <option value="Excise Sub-Inspector">Excise Sub-Inspector</option>
                    <option value="Excise Inspector">Excise Inspector</option>
                    <option value="Superintendent of Excise">Superintendent of Excise</option>
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Badge Number</label>
                  <input
                    type="text"
                    value={newEmp.badge_number}
                    onChange={(e) => setNewEmp({ ...newEmp, badge_number: e.target.value })}
                    placeholder="e.g. EXC-AP-301"
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-500 shadow-sm"
                >
                  {submitting ? 'Creating...' : 'Create Officer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
