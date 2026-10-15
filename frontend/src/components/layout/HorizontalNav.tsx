import React, { useState, useRef, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
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
  ChevronDown,
  Menu,
  X,
  Shield,
  Layers,
  Cpu,
  Search,
  CheckCircle2
} from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';

interface SubItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description?: string;
  badge?: string;
  requiredRoles?: string[];
}

interface NavCategory {
  id: string;
  title: string;
  subItems: SubItem[];
}

export const HorizontalNav: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const location = useLocation();

  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Grouped navigation matching official Andhra Pradesh e-Pragati / Departmental portal standards
  const navCategories: NavCategory[] = [
    {
      id: 'home',
      title: 'Home',
      subItems: [
        {
          path: '/',
          label: t.nav.dashboard,
          icon: LayoutDashboard,
          description: 'Key departmental metrics, statistics, and pending case status'
        },
        {
          path: '/reports',
          label: t.nav.reportsAnalytics,
          icon: BarChart3,
          description: 'District and state-level trends, seizure analytics & exports'
        },
        {
          path: '/settings',
          label: t.nav.settingsHealth,
          icon: Settings,
          description: 'System connectivity, backup verification & security diagnostics'
        }
      ]
    },
    {
      id: 'case_management',
      title: 'Case Management',
      subItems: [
        {
          path: '/cases',
          label: t.nav.caseManagement,
          icon: FolderOpen,
          description: 'Browse, filter, and review u-FIR files and case provenance'
        },
        {
          path: '/intake',
          label: t.nav.newCaseIntake,
          icon: FilePlus,
          description: 'Register a new u-FIR manually or auto-extract from scanned PDF'
        },
        {
          path: '/bulk-ingestion',
          label: t.nav.bulkIngestion,
          icon: UploadCloud,
          description: 'Batch upload legacy records, PDFs, CSV, or scanned FIR documents'
        }
      ]
    },
    {
      id: 'ai_legal',
      title: 'AI & Legal Intelligence',
      subItems: [
        {
          path: '/ai-fir-assistance',
          label: t.nav.aiFirAssistance,
          icon: BotMessageSquare,
          description: 'PDF-only grounded RAG with exact physical page citations & validation',
          badge: 'Grounded RAG'
        },
        {
          path: '/summaries',
          label: t.nav.aiCaseSummaries,
          icon: Sparkles,
          description: 'Generate multi-lingual executive briefs and trial synopses'
        },
        {
          path: '/legal',
          label: t.nav.legalSectionAssistance,
          icon: Scale,
          description: 'Statutory section recommendation engine (AP Excise & NDPS Acts)'
        }
      ]
    },
    {
      id: 'investigation',
      title: 'Investigation Tools',
      subItems: [
        {
          path: '/network',
          label: t.nav.entityNetwork,
          icon: Share2,
          description: 'Interactive syndicate & suspect graph across multi-station cases'
        },
        {
          path: '/entity-review',
          label: t.nav.entityReviewQueue,
          icon: UsersRound,
          description: 'Review and merge duplicate criminal and vehicle entities'
        },
        {
          path: '/case-diary',
          label: t.nav.caseDiaryGenerator,
          icon: BookOpen,
          description: 'Generate statutory Section 172 CrPC daily investigation diary'
        },
        {
          path: '/chargesheet',
          label: t.nav.chargesheetGenerator,
          icon: FileSpreadsheet,
          description: 'Auto-compile formal court chargesheet from verified case facts'
        }
      ]
    },
    {
      id: 'admin',
      title: 'Administration',
      subItems: [
        {
          path: '/employees',
          label: t.nav.employeeManagement,
          icon: UserCheck,
          description: 'Officer directory, pending self-registrations & jurisdiction management',
          requiredRoles: ['DISTRICT', 'STATE']
        },
        {
          path: '/audit-trail',
          label: t.nav.auditTrail,
          icon: ShieldAlert,
          description: 'Tamper-evident SHA-256 recursive cryptographic hash chain'
        }
      ]
    }
  ];

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpenDropdown(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close dropdown on route change
  useEffect(() => {
    setOpenDropdown(null);
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const isCategoryActive = (category: NavCategory) => {
    return category.subItems.some((item) =>
      item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path)
    );
  };

  return (
    <nav className="bg-[#112d4e] text-white border-b border-slate-700 shadow-md relative z-20 select-none">
      <div className="max-w-[1700px] mx-auto px-4 sm:px-6 flex items-center justify-between" ref={dropdownRef}>
        {/* Desktop Menu Categories */}
        <div className="hidden lg:flex items-center space-x-1">
          {navCategories.map((category) => {
            const active = isCategoryActive(category);
            const isOpen = openDropdown === category.id;

            return (
              <div key={category.id} className="relative">
                <button
                  type="button"
                  onClick={() => setOpenDropdown(isOpen ? null : category.id)}
                  onMouseEnter={() => setOpenDropdown(category.id)}
                  className={`flex items-center space-x-1.5 px-4 py-3 text-sm font-semibold transition-all duration-150 border-b-2 ${
                    active
                      ? 'border-amber-400 text-amber-300 bg-white/10'
                      : isOpen
                      ? 'border-emerald-400 text-emerald-300 bg-white/5'
                      : 'border-transparent text-slate-200 hover:text-white hover:bg-white/5'
                  }`}
                  aria-expanded={isOpen}
                >
                  <span>{category.title}</span>
                  <ChevronDown
                    className={`w-4 h-4 transition-transform duration-200 ${
                      isOpen ? 'rotate-180 text-amber-400' : 'text-slate-400'
                    }`}
                  />
                </button>

                {/* Dropdown Menu Overlay */}
                {isOpen && (
                  <div
                    onMouseLeave={() => setOpenDropdown(null)}
                    className="absolute left-0 top-full mt-0 w-80 bg-white text-slate-800 rounded-b-lg shadow-xl border border-slate-200 py-2 animate-in fade-in slide-in-from-top-1 duration-150 z-50"
                  >
                    <div className="px-3 py-1.5 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      {category.title}
                    </div>
                    <div className="py-1">
                      {category.subItems.map((item) => {
                        if (item.requiredRoles && user && !item.requiredRoles.includes(user.role)) {
                          return null;
                        }
                        const Icon = item.icon;
                        const isSubActive =
                          item.path === '/'
                            ? location.pathname === '/'
                            : location.pathname.startsWith(item.path);

                        return (
                          <NavLink
                            key={item.path}
                            to={item.path}
                            className={`flex items-start space-x-3 px-3.5 py-2.5 hover:bg-emerald-50 transition-colors ${
                              isSubActive ? 'bg-emerald-50/80 text-[#0f5132] font-semibold' : 'text-slate-700'
                            }`}
                          >
                            <div
                              className={`p-1.5 rounded-md mt-0.5 ${
                                isSubActive
                                  ? 'bg-[#0f5132] text-white shadow-xs'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              <Icon className="w-4 h-4" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <span className="text-sm leading-tight text-slate-900">{item.label}</span>
                                {item.badge && (
                                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300">
                                    {item.badge}
                                  </span>
                                )}
                              </div>
                              {item.description && (
                                <p className="text-xs text-slate-500 line-clamp-1 mt-0.5">
                                  {item.description}
                                </p>
                              )}
                            </div>
                          </NavLink>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Quick Portal Action Buttons on Right */}
        <div className="hidden md:flex items-center space-x-2 py-2">
          <NavLink
            to="/ai-fir-assistance"
            className="flex items-center space-x-1.5 bg-gradient-to-r from-emerald-600 to-[#0f5132] text-white text-xs font-bold px-3 py-1.5 rounded-md shadow hover:brightness-110 transition-all border border-emerald-500"
          >
            <BotMessageSquare className="w-3.5 h-3.5 text-amber-300" />
            <span>AI FIR RAG Assistant</span>
          </NavLink>
          <NavLink
            to="/intake"
            className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-semibold px-3 py-1.5 rounded-md border border-slate-600 transition-colors"
          >
            <FilePlus className="w-3.5 h-3.5 text-emerald-400" />
            <span>+ New Case</span>
          </NavLink>
        </div>

        {/* Mobile Hamburger Toggle */}
        <div className="flex lg:hidden items-center justify-between w-full py-2.5">
          <span className="text-sm font-bold text-amber-300">Department Navigation Menu</span>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-1.5 rounded-md text-slate-200 hover:text-white hover:bg-slate-800 focus:outline-none"
            aria-label="Toggle navigation"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden bg-slate-900 border-t border-slate-700 px-4 py-3 space-y-4 max-h-[80vh] overflow-y-auto">
          {navCategories.map((category) => (
            <div key={category.id} className="space-y-1">
              <div className="text-xs font-bold uppercase tracking-wider text-amber-400 px-2 py-1">
                {category.title}
              </div>
              <div className="space-y-0.5">
                {category.subItems.map((item) => {
                  if (item.requiredRoles && user && !item.requiredRoles.includes(user.role)) {
                    return null;
                  }
                  const Icon = item.icon;
                  const isSubActive =
                    item.path === '/'
                      ? location.pathname === '/'
                      : location.pathname.startsWith(item.path);

                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`flex items-center space-x-3 px-3 py-2 rounded-md text-sm transition-colors ${
                        isSubActive
                          ? 'bg-[#0f5132] text-white font-semibold'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      <Icon className="w-4 h-4 text-emerald-400" />
                      <span>{item.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </nav>
  );
};
