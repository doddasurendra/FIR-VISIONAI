import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import {
  UserCheck,
  UserPlus,
  Shield,
  CheckCircle,
  XCircle,
  AlertCircle
} from 'lucide-react';

export const EmployeeManagement: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();

  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
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
    designation: 'Excise Sub-Inspector'
  });
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchEmployees = async () => {
    try {
      setLoading(true);
      const res = await api.get('/employees/');
      setEmployees(res.data);
    } catch (e) {
      console.error('Failed to load employees:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmployees();
  }, [user]);

  const handleToggleStatus = async (id: string) => {
    try {
      await api.put(`/employees/${id}/toggle-status`);
      await fetchEmployees();
    } catch (e: any) {
      alert('Toggle error: ' + (e.response?.data?.detail || e.message));
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
        designation: 'Excise Sub-Inspector'
      });
      await fetchEmployees();
    } catch (e: any) {
      setErrorMsg(e.response?.data?.detail || 'Failed to create employee');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <UserCheck className="w-5 h-5 text-blue-600" />
            <span>{t.nav.employeeManagement}</span>
          </h2>
          <p className="text-xs text-slate-500">
            Section 5: Station & District Officer Credentials & Hierarchical Scope Administration
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
        >
          <UserPlus className="w-4 h-4" />
          <span>Add Officer</span>
        </button>
      </div>

      {/* Employees Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
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
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {employees.map((emp) => (
                  <tr key={emp.id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-3.5 font-medium">
                      <div className="font-bold text-slate-900">{emp.full_name}</div>
                      <div className="text-[11px] text-slate-400 font-mono">@{emp.username}</div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800 border border-blue-200">
                        {emp.role}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="font-semibold text-slate-800">{emp.station || 'All District Stations'}</div>
                      <div className="text-[11px] text-slate-400">{emp.district} District</div>
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
                    <td className="px-5 py-3.5 text-right">
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

      {/* Add Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 space-y-4 border border-slate-200">
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
                  <label className="block font-semibold text-slate-700 mb-1">Username</label>
                  <input
                    type="text"
                    required
                    value={newEmp.username}
                    onChange={(e) => setNewEmp({ ...newEmp, username: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Email</label>
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
                  <label className="block font-semibold text-slate-700 mb-1">Full Officer Name</label>
                  <input
                    type="text"
                    required
                    value={newEmp.full_name}
                    onChange={(e) => setNewEmp({ ...newEmp, full_name: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Initial Password</label>
                  <input
                    type="password"
                    required
                    value={newEmp.password}
                    onChange={(e) => setNewEmp({ ...newEmp, password: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Role Jurisdiction Scope</label>
                  <select
                    value={newEmp.role}
                    onChange={(e) => setNewEmp({ ...newEmp, role: e.target.value })}
                    className="w-full border border-slate-300 rounded-lg p-2 bg-white"
                  >
                    <option value="STATION">STATION (Assigned Station Only)</option>
                    <option value="DISTRICT">DISTRICT (District Wide)</option>
                    {user?.role === 'STATE' && <option value="STATE">STATE (All Districts)</option>}
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Assigned Station</label>
                  <input
                    type="text"
                    required
                    value={newEmp.station}
                    onChange={(e) => setNewEmp({ ...newEmp, station: e.target.value })}
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
