import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, Lock, User, AlertCircle, ArrowRight } from 'lucide-react';

export const Login: React.FC = () => {
  const { login, switchDemoUser } = useAuth();
  const [username, setUsername] = useState('station_officer');
  const [password, setPassword] = useState('StationPass@2024');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const success = await login(username, password);
    if (!success) {
      setError('Invalid officer username or credentials. Please check password.');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border border-slate-700">
        {/* Department Banner */}
        <div className="bg-gradient-to-r from-blue-900 to-slate-900 text-white p-8 text-center space-y-3">
          <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto shadow-lg shadow-blue-500/30">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">FIR Sahayak</h1>
            <p className="text-xs text-blue-300 font-medium mt-0.5">
              Andhra Pradesh Prohibition & Excise Department
            </p>
          </div>
          <span className="inline-block text-[10px] bg-blue-500/20 text-blue-200 border border-blue-400/30 px-2 py-0.5 rounded-full font-mono">
            u-FIR AI Platform v1.0
          </span>
        </div>

        {/* Login Form */}
        <div className="p-8 space-y-6">
          {error && (
            <div className="p-3 bg-red-50 text-red-700 rounded-lg text-xs flex items-center gap-2 border border-red-200">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Officer Username</label>
              <div className="relative">
                <User className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full pl-9 pr-3 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium"
                />
              </div>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-9 pr-3 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <span>{loading ? 'Authenticating...' : 'Sign In with Credentials'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {/* Quick Demo Switcher Buttons */}
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wide">
              Quick Demo Access (1-Click Switch):
            </span>
            <div className="grid grid-cols-3 gap-2 text-[11px]">
              <button
                type="button"
                onClick={() => switchDemoUser('STATION')}
                className="p-2 bg-slate-50 hover:bg-blue-50 hover:border-blue-300 rounded-lg border border-slate-200 text-center font-medium text-slate-700 transition-colors"
              >
                <div className="font-bold text-blue-700">Station</div>
                <div className="text-[9px] text-slate-400">Kurnool Town</div>
              </button>
              <button
                type="button"
                onClick={() => switchDemoUser('DISTRICT')}
                className="p-2 bg-slate-50 hover:bg-blue-50 hover:border-blue-300 rounded-lg border border-slate-200 text-center font-medium text-slate-700 transition-colors"
              >
                <div className="font-bold text-indigo-700">District</div>
                <div className="text-[9px] text-slate-400">Kurnool Dist</div>
              </button>
              <button
                type="button"
                onClick={() => switchDemoUser('STATE')}
                className="p-2 bg-slate-50 hover:bg-blue-50 hover:border-blue-300 rounded-lg border border-slate-200 text-center font-medium text-slate-700 transition-colors"
              >
                <div className="font-bold text-purple-700">State</div>
                <div className="text-[9px] text-slate-400">Headquarters</div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
