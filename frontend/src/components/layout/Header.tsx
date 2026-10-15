import React from 'react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';
import { Globe, User as UserIcon, LogOut, ShieldCheck, RefreshCw } from 'lucide-react';

export const Header: React.FC = () => {
  const { language, setLanguage, t } = useLanguage();
  const { user, logout, switchDemoUser } = useAuth();

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shadow-sm z-10">
      {/* Title & Department Status */}
      <div className="flex items-center space-x-3">
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Government of Andhra Pradesh
          </span>
          <h2 className="text-sm font-bold text-slate-800">
            Unified First Information Report (u-FIR) Intelligence System
          </h2>
        </div>
      </div>

      {/* Controls & User Profile */}
      <div className="flex items-center space-x-4">
        {/* Language Selector */}
        <div className="flex items-center space-x-1.5 bg-slate-100 rounded-lg p-1 border border-slate-200 text-xs">
          <Globe className="w-3.5 h-3.5 text-slate-500 ml-1.5" />
          <button
            onClick={() => setLanguage('en')}
            className={`px-2 py-1 rounded font-medium transition-colors ${
              language === 'en' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            English
          </button>
          <button
            onClick={() => setLanguage('te')}
            className={`px-2 py-1 rounded font-medium transition-colors font-telugu ${
              language === 'te' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            తెలుగు
          </button>
          <button
            onClick={() => setLanguage('hi')}
            className={`px-2 py-1 rounded font-medium transition-colors ${
              language === 'hi' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            हिन्दी
          </button>
        </div>

        {/* Demo Role Switcher (Convenient for Hackathon & Live Jury Demonstrations) */}
        <div className="hidden lg:flex items-center space-x-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
          <span className="text-[11px] text-slate-500 font-medium px-1.5">Role Switch:</span>
          <button
            onClick={() => switchDemoUser('STATION')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium ${
              user?.role === 'STATION' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-200'
            }`}
          >
            Station
          </button>
          <button
            onClick={() => switchDemoUser('DISTRICT')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium ${
              user?.role === 'DISTRICT' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-200'
            }`}
          >
            District
          </button>
          <button
            onClick={() => switchDemoUser('STATE')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium ${
              user?.role === 'STATE' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-200'
            }`}
          >
            State
          </button>
        </div>

        {/* User Card */}
        <div className="flex items-center space-x-3 pl-2 border-l border-slate-200">
          <div className="w-8 h-8 rounded-full bg-blue-100 border border-blue-300 flex items-center justify-center text-blue-700 font-semibold text-xs">
            {user?.full_name ? user.full_name[0] : 'O'}
          </div>
          <div className="hidden sm:block text-left text-xs">
            <p className="font-semibold text-slate-800 leading-tight">{user?.full_name || 'Officer'}</p>
            <p className="text-slate-500">{user?.designation || 'Excise Officer'}</p>
          </div>
          <button
            onClick={logout}
            title="Log Out"
            className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
