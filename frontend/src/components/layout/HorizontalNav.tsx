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
  CheckCircle2,
  Folders,
  User,
  Users,
  Clock,
  FlaskConical,
  Truck,
  Car,
  AlertTriangle,
  Zap,
  UserSearch,
  Monitor,
  Crosshair,
  Landmark,
  Home,
} from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';
import api from '../../api/client';

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

  const [folderCounts, setFolderCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    // Fetch folder counts once on mount (static import used above)
    api.get<Record<string, number>>('/folders/counts')
      .then(res => setFolderCounts(res.data))
      .catch(() => {}); // Silently ignore if folders endpoint not yet available
  }, []);

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
          path: '/document-extraction',
          label: 'FIR Document Extraction',
          icon: Sparkles,
          description: 'Multimodal AI extraction workspace with side-by-side viewer & config',
          badge: 'AI Workspace'
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

        {/* All FIR Folders Dropdown — placed immediately after nav categories */}
        <div className="hidden lg:block relative ml-2">
          <button
            type="button"
            onClick={() => setOpenDropdown(openDropdown === 'fir_folders' ? null : 'fir_folders')}
            onMouseEnter={() => setOpenDropdown('fir_folders')}
            className={`flex items-center space-x-1.5 px-4 py-3 text-sm font-semibold transition-all duration-150 border-b-2 ${
              location.pathname.startsWith('/folders')
                ? 'border-amber-400 text-amber-300 bg-white/10'
                : openDropdown === 'fir_folders'
                ? 'border-emerald-400 text-emerald-300 bg-white/5'
                : 'border-transparent text-slate-200 hover:text-white hover:bg-white/5'
            }`}
            aria-expanded={openDropdown === 'fir_folders'}
          >
            <Folders className="w-4 h-4" />
            <span>All FIR Folders</span>
            <ChevronDown
              className={`w-4 h-4 transition-transform duration-200 ${
                openDropdown === 'fir_folders' ? 'rotate-180 text-amber-400' : 'text-slate-400'
              }`}
            />
          </button>

          {openDropdown === 'fir_folders' && (
            <div
              onMouseLeave={() => setOpenDropdown(null)}
              className="absolute left-0 top-full mt-0 w-[520px] bg-white text-slate-800 rounded-b-lg shadow-xl border border-slate-200 py-2 z-50 animate-in fade-in slide-in-from-top-1 duration-150"
            >
              <div className="px-3 py-1.5 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                FIR Folder Categories
              </div>

              {/* FIR Types group */}
              <div className="px-3 pt-2 pb-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">FIR Types</div>
                <div className="grid grid-cols-2 gap-0.5">
                  {[
                    { slug: 'illicit-distillation', name: 'Illicit Distillation', color: '#7c3aed' },
                    { slug: 'ndps-transport', name: 'NDPS / Drug Transport', color: '#dc2626' },
                    { slug: 'non-duty-paid-liquor', name: 'Non-Duty-Paid Liquor', color: '#b45309' },
                    { slug: 'vehicle-seizure', name: 'Vehicle Seizure', color: '#0891b2' },
                    { slug: 'unlawful-possession', name: 'Unlawful Possession', color: '#4f46e5' },
                    { slug: 'theft', name: 'Theft / Property Crime', color: '#ca8a04' },
                    { slug: 'assault', name: 'Assault / Bodily Harm', color: '#e11d48' },
                    { slug: 'road-accident', name: 'Road / Traffic Accidents', color: '#ea580c' },
                    { slug: 'cheating-fraud', name: 'Cheating / Fraud', color: '#059669' },
                    { slug: 'public-nuisance', name: 'Public Nuisance', color: '#6b7280' },
                    { slug: 'missing-person', name: 'Missing Person Reports', color: '#0f5132' },
                    { slug: 'domestic-violence', name: 'Domestic Violence', color: '#be185d' },
                    { slug: 'land-property', name: 'Land / Property Dispute', color: '#15803d' },
                    { slug: 'cyber-crime', name: 'Cyber Crime', color: '#1d4ed8' },
                    { slug: 'death-investigation', name: 'Death / Unnatural Death', color: '#374151' },
                    { slug: 'arms-explosives', name: 'Arms & Explosives', color: '#b91c1c' },
                    { slug: 'sexual-offence', name: 'Sexual Offence Cases', color: '#9f1239' },
                  ].map(folder => (
                    <NavLink
                      key={folder.slug}
                      to={`/folders/${folder.slug}`}
                      className={({ isActive }) =>
                        `flex items-center justify-between px-2.5 py-1.5 rounded hover:bg-slate-50 transition-colors ${
                          isActive ? 'bg-emerald-50/80 text-[#0f5132] font-semibold' : 'text-slate-700'
                        }`
                      }
                    >
                      <div className="flex items-center space-x-2">
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: folder.color }}
                        />
                        <span className="text-xs">{folder.name}</span>
                      </div>
                      {folderCounts[folder.slug] != null && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                          {folderCounts[folder.slug]}
                        </span>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>

              {/* Person-Based group */}
              <div className="px-3 py-1 border-t border-slate-100">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Person-Based Folders</div>
                <div className="grid grid-cols-2 gap-0.5">
                  <NavLink
                    to="/folders/persons/single-fir"
                    className={({ isActive }) =>
                      `flex items-center justify-between px-2.5 py-1.5 rounded hover:bg-slate-50 transition-colors ${
                        isActive ? 'bg-emerald-50/80 text-[#0f5132] font-semibold' : 'text-slate-700'
                      }`
                    }
                  >
                    <div className="flex items-center space-x-2">
                      <User className="w-3 h-3 text-blue-500" />
                      <span className="text-xs">Single-FIR Persons</span>
                    </div>
                    {folderCounts['single-fir-persons'] != null && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                        {folderCounts['single-fir-persons']}
                      </span>
                    )}
                  </NavLink>
                  <NavLink
                    to="/folders/persons/multiple-fir"
                    className={({ isActive }) =>
                      `flex items-center justify-between px-2.5 py-1.5 rounded hover:bg-slate-50 transition-colors ${
                        isActive ? 'bg-emerald-50/80 text-[#0f5132] font-semibold' : 'text-slate-700'
                      }`
                    }
                  >
                    <div className="flex items-center space-x-2">
                      <Users className="w-3 h-3 text-amber-600" />
                      <span className="text-xs">Multiple-FIR Persons</span>
                    </div>
                    {folderCounts['multiple-fir-persons'] != null && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                        {folderCounts['multiple-fir-persons']}
                      </span>
                    )}
                  </NavLink>
                </div>
              </div>

              {/* Status group */}
              <div className="px-3 py-1 border-t border-slate-100">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Status Folders</div>
                <div className="grid grid-cols-3 gap-0.5">
                  {[
                    { slug: 'pending-classification', name: 'Pending Classification', color: '#d97706' },
                    { slug: 'under-investigation', name: 'Under Investigation', color: '#2563eb' },
                    { slug: 'closed-cases', name: 'Closed / Charge-sheeted', color: '#16a34a' },
                  ].map(folder => (
                    <NavLink
                      key={folder.slug}
                      to={`/folders/${folder.slug}`}
                      className={({ isActive }) =>
                        `flex items-center justify-between px-2.5 py-1.5 rounded hover:bg-slate-50 transition-colors ${
                          isActive ? 'bg-emerald-50/80 text-[#0f5132] font-semibold' : 'text-slate-700'
                        }`
                      }
                    >
                      <div className="flex items-center space-x-2">
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: folder.color }}
                        />
                        <span className="text-xs">{folder.name}</span>
                      </div>
                      {folderCounts[folder.slug] != null && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                          {folderCounts[folder.slug]}
                        </span>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Quick Portal Action Buttons on Right */}
        <div className="hidden md:flex items-center space-x-2 py-2">
          <NavLink
            to="/document-extraction"
            className="flex items-center space-x-1.5 bg-blue-900/80 hover:bg-blue-800 text-white text-xs font-semibold px-2.5 py-1.5 rounded-md border border-blue-600 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            <span>AI Extraction</span>
          </NavLink>
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
          {/* Mobile Quick Action Shortcuts */}
          <div className="grid grid-cols-3 gap-2 pb-3 border-b border-slate-800">
            <NavLink
              to="/intake"
              onClick={() => setMobileMenuOpen(false)}
              className="flex flex-col items-center justify-center p-2 rounded-lg bg-emerald-800/90 hover:bg-emerald-700 text-white text-[11px] font-bold shadow text-center border border-emerald-600 transition-colors"
            >
              <FilePlus className="w-4 h-4 text-emerald-300 mb-1" />
              <span>+ New Case</span>
            </NavLink>
            <NavLink
              to="/document-extraction"
              onClick={() => setMobileMenuOpen(false)}
              className="flex flex-col items-center justify-center p-2 rounded-lg bg-blue-900/90 hover:bg-blue-800 text-white text-[11px] font-bold shadow text-center border border-blue-700 transition-colors"
            >
              <Sparkles className="w-4 h-4 text-amber-300 mb-1" />
              <span>AI Extraction</span>
            </NavLink>
            <NavLink
              to="/ai-fir-assistance"
              onClick={() => setMobileMenuOpen(false)}
              className="flex flex-col items-center justify-center p-2 rounded-lg bg-gradient-to-br from-emerald-600 to-[#0f5132] text-white text-[11px] font-bold shadow text-center border border-emerald-500 transition-colors"
            >
              <BotMessageSquare className="w-4 h-4 text-amber-300 mb-1" />
              <span>RAG Copilot</span>
            </NavLink>
          </div>

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

          {/* All FIR Folders in mobile menu */}
          <div className="space-y-1">
            <div className="text-xs font-bold uppercase tracking-wider text-amber-400 px-2 py-1">
              All FIR Folders
            </div>
            <div className="space-y-0.5">
              {[
                { to: '/folders/illicit-distillation', label: 'Illicit Distillation' },
                { to: '/folders/ndps-transport', label: 'NDPS / Drug Transport' },
                { to: '/folders/non-duty-paid-liquor', label: 'Non-Duty-Paid Liquor' },
                { to: '/folders/theft', label: 'Theft / Property Crime' },
                { to: '/folders/assault', label: 'Assault / Bodily Harm' },
                { to: '/folders/road-accident', label: 'Road / Traffic Accidents' },
                { to: '/folders/cheating-fraud', label: 'Cheating / Fraud' },
                { to: '/folders/cyber-crime', label: 'Cyber Crime' },
                { to: '/folders/vehicle-seizure', label: 'Vehicle Seizure Cases' },
                { to: '/folders/missing-person', label: 'Missing Person Reports' },
                { to: '/folders/persons/single-fir', label: 'Single-FIR Persons' },
                { to: '/folders/persons/multiple-fir', label: 'Multiple-FIR Persons' },
                { to: '/folders/pending-classification', label: 'Pending Classification' },
                { to: '/folders/under-investigation', label: 'Under Investigation' },
                { to: '/folders/closed-cases', label: 'Closed / Charge-sheeted' },
              ].map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center space-x-3 px-3 py-2 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-[#0f5132] text-white font-semibold'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                    }`
                  }
                >
                  <Folders className="w-4 h-4 text-emerald-400" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
};
