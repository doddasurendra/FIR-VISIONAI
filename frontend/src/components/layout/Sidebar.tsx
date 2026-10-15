import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderOpen,
  FilePlus,
  Sparkles,
  Scale,
  Share2,
  UsersRound,
  BookOpen,
  FileSpreadsheet,
  BotMessageSquare,
  UploadCloud,
  UserCheck,
  ShieldAlert,
  BarChart3,
  Settings,
  Shield
} from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';

export const Sidebar: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();

  const navItems = [
    { path: '/', label: t.nav.dashboard, icon: LayoutDashboard },
    { path: '/cases', label: t.nav.caseManagement, icon: FolderOpen },
    { path: '/intake', label: t.nav.newCaseIntake, icon: FilePlus },
    { path: '/summaries', label: t.nav.aiCaseSummaries, icon: Sparkles },
    { path: '/legal', label: t.nav.legalSectionAssistance, icon: Scale },
    { path: '/network', label: t.nav.entityNetwork, icon: Share2 },
    { path: '/entity-review', label: t.nav.entityReviewQueue, icon: UsersRound },
    { path: '/case-diary', label: t.nav.caseDiaryGenerator, icon: BookOpen },
    { path: '/chargesheet', label: t.nav.chargesheetGenerator, icon: FileSpreadsheet },
    { path: '/ai-fir-assistance', label: t.nav.aiFirAssistance, icon: BotMessageSquare, highlight: true },
    { path: '/bulk-ingestion', label: t.nav.bulkIngestion, icon: UploadCloud },
    { path: '/employees', label: t.nav.employeeManagement, icon: UserCheck, requiredRoles: ['DISTRICT', 'STATE'] },
    { path: '/audit-trail', label: t.nav.auditTrail, icon: ShieldAlert },
    { path: '/reports', label: t.nav.reportsAnalytics, icon: BarChart3 },
    { path: '/settings', label: t.nav.settingsHealth, icon: Settings }
  ];

  return (
    <aside className="w-72 bg-slate-900 text-slate-200 flex flex-col h-screen border-r border-slate-800 select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-800 flex items-center space-x-3 bg-slate-950">
        <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-md shadow-blue-500/20">
          <Shield className="w-6 h-6" />
        </div>
        <div>
          <h1 className="font-bold text-base tracking-wide text-white flex items-center gap-1.5">
            {t.appTitle}
            <span className="text-[10px] bg-blue-600/30 text-blue-400 px-1.5 py-0.5 rounded font-mono border border-blue-500/30">u-FIR</span>
          </h1>
          <p className="text-xs text-slate-400 leading-tight">AP Prohibition & Excise</p>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1 custom-scrollbar text-sm font-medium">
        {navItems.map((item) => {
          if (item.requiredRoles && user && !item.requiredRoles.includes(user.role)) {
            return null;
          }
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-all duration-150 ${
                  isActive
                    ? 'bg-blue-600 text-white font-semibold shadow-sm'
                    : item.highlight
                    ? 'bg-blue-950/60 text-blue-300 hover:bg-blue-900/50 border border-blue-500/30'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Scope Footer Badge */}
      <div className="p-4 border-t border-slate-800 bg-slate-950 text-xs">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span>Active Data Scope:</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            {user?.role || 'STATION'}
          </span>
        </div>
        <p className="text-slate-200 font-medium truncate">
          {user?.station ? `${user.station}, ${user.district}` : user?.district || 'State Headquarters'}
        </p>
      </div>
    </aside>
  );
};
