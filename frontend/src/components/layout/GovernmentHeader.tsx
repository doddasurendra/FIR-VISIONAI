import React, { useState } from 'react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';
import { Globe, LogOut, Shield, ShieldCheck, MapPin, Building2, User as UserIcon, ZoomIn } from 'lucide-react';
import { LogoZoomModal } from '../common/LogoZoomModal';

export const GovernmentHeader: React.FC = () => {
  const { language, setLanguage, t } = useLanguage();
  const { user, logout, switchDemoUser } = useAuth();
  const [isLogoModalOpen, setIsLogoModalOpen] = useState<boolean>(false);

  return (
    <header className="bg-white border-b border-slate-200 select-none shadow-sm z-30 sticky top-0">
      {/* Official Government of AP Green Top Ribbon */}
      <div className="bg-[#0f5132] text-white px-4 sm:px-6 py-1.5 flex flex-wrap items-center justify-between text-xs border-b border-emerald-800">
        <div className="flex items-center space-x-3">
          {/* AP Government Logo in ribbon */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setIsLogoModalOpen(true)}
              title="Click to zoom official emblem"
              className="flex items-center space-x-2 text-left cursor-pointer hover:opacity-90 transition-opacity"
            >
              <img
                src="/assets/andhra-pradesh-government-logo.jpg"
                alt="Government of Andhra Pradesh — Andhra Pradesh Emblem, State Map and Dhyana Buddha Statue, Amaravati"
                className="h-5 w-auto object-contain rounded-sm"
              />
              <span className="font-semibold tracking-wide text-emerald-50">
                GOVERNMENT OF ANDHRA PRADESH &bull; ఆంధ్రప్రదేశ్ ప్రభుత్వం
              </span>
            </button>
          </div>
          <span className="hidden md:inline-block text-emerald-300">|</span>
          <span className="hidden md:inline-block text-emerald-100 font-medium">
            Prohibition & Excise Department &bull; ప్రొహిబిషన్ & ఎక్సైజ్ శాఖ
          </span>
        </div>

        {/* Live Scope Indicator */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 bg-emerald-900/60 px-2.5 py-0.5 rounded text-[11px] border border-emerald-700/50">
            <ShieldCheck className="w-3.5 h-3.5 text-amber-300" />
            <span className="text-emerald-200">Jurisdiction Scope:</span>
            <span className="font-bold text-amber-300 uppercase">{user?.role || 'STATION'}</span>
          </div>
          <div className="hidden sm:flex items-center space-x-1 text-emerald-100 text-[11px]">
            <MapPin className="w-3 h-3 text-emerald-300" />
            <span className="truncate max-w-[200px]">
              {user?.station ? `${user.station}, ${user.district}` : user?.district || 'State Headquarters, Amaravati'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Government Portal Header Area */}
      <div className="max-w-[1700px] mx-auto px-4 sm:px-6 py-2 sm:py-3 flex flex-wrap lg:flex-nowrap items-center justify-between gap-3 sm:gap-4">
        {/* Brand & Department Emblem */}
        <div className="flex items-center space-x-3.5 sm:space-x-4">
          {/* Clickable and Zoomable Header Logo (88–100px on desktop, responsive) */}
          <button
            type="button"
            onClick={() => setIsLogoModalOpen(true)}
            title="Click to inspect and zoom Government Emblem"
            aria-label="Government of Andhra Pradesh Emblem — Click to enlarge and zoom"
            className="relative group p-1 sm:p-1.5 rounded-xl bg-white border border-emerald-600/70 shadow-sm hover:shadow-md hover:border-emerald-600 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 cursor-pointer flex-shrink-0"
          >
            <img
              src="/assets/andhra-pradesh-government-logo.jpg"
              alt="Government of Andhra Pradesh Emblem"
              className="h-14 sm:h-20 lg:h-[92px] w-auto object-contain transition-transform group-hover:scale-[1.02]"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
                const parent = (e.target as HTMLImageElement).parentElement;
                if (parent) {
                  parent.classList.add('bg-gradient-to-br', 'from-[#0f5132]', 'to-[#198754]');
                  parent.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-10 h-10 text-amber-300"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
                }
              }}
            />
            <span className="absolute bottom-1 right-1 bg-slate-900/80 text-white rounded p-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow">
              <ZoomIn className="w-3.5 h-3.5" />
            </span>
          </button>

          <div className="flex flex-col justify-center">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-slate-900 flex items-center gap-2">
                FIR VisionAI
              </h1>
              <span className="text-[11px] bg-emerald-100 text-[#0f5132] font-bold px-2 py-0.5 rounded border border-emerald-300 font-mono">
                u-FIR v2.0
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-700 font-semibold mt-0.5">
              Unified FIR & AI-Powered Case Intelligence Platform
            </p>
            <p className="text-[11px] text-slate-500 font-medium hidden sm:block">
              Andhra Pradesh Prohibition & Excise Department &bull; See the Evidence. Connect the Cases. Support Better Decisions.
            </p>
          </div>
        </div>

        {/* Right Controls: Role Switcher, Language, and Officer Profile */}
        <div className="flex items-center space-x-3 sm:space-x-4 flex-shrink-0">
          {/* Quick Role Switcher Pill (Live Demo / Verification) */}
          <div className="hidden xl:flex items-center space-x-1 bg-slate-50 p-1 rounded-lg border border-slate-200 text-xs shadow-inner">
            <span className="text-[11px] text-slate-500 font-medium px-1.5">Demo Role:</span>
            <button
              onClick={() => switchDemoUser('DEV')}
              title="Full Developer Access with all diagnostics"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all ${
                user?.username === 'developer_test'
                  ? 'bg-amber-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              Dev
            </button>
            <button
              onClick={() => switchDemoUser('STATION')}
              title="Station Officer - Scoped to Bhimavaram Station"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all ${
                user?.role === 'STATION' && user?.username !== 'developer_test'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              Station
            </button>
            <button
              onClick={() => switchDemoUser('DISTRICT')}
              title="District Officer - Scoped to West Godavari District"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all ${
                user?.role === 'DISTRICT'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              District
            </button>
            <button
              onClick={() => switchDemoUser('STATE')}
              title="State Commissionerate - Statewide Visibility"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all ${
                user?.role === 'STATE' && user?.username !== 'developer_test'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              State
            </button>
          </div>

          {/* Language Selector */}
          <div className="flex items-center space-x-1 bg-slate-100 rounded-lg p-0.5 border border-slate-200 text-xs">
            <Globe className="w-3.5 h-3.5 text-slate-500 ml-1.5 hidden sm:inline" />
            <button
              onClick={() => setLanguage('en')}
              className={`px-2 py-1 rounded font-semibold text-xs transition-colors ${
                language === 'en'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              EN
            </button>
            <button
              onClick={() => setLanguage('te')}
              className={`px-2 py-1 rounded font-semibold text-xs font-telugu transition-colors ${
                language === 'te'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              తెలుగు
            </button>
            <button
              onClick={() => setLanguage('hi')}
              className={`px-2 py-1 rounded font-semibold text-xs transition-colors ${
                language === 'hi'
                  ? 'bg-[#0f5132] text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              हिन्दी
            </button>
          </div>

          {/* Officer Profile Card */}
          <div className="flex items-center space-x-2.5 pl-3 border-l border-slate-200">
            <div className="w-9 h-9 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center text-[#0f5132] font-bold text-xs shadow-xs">
              {user?.full_name ? user.full_name[0] : 'O'}
            </div>
            <div className="hidden sm:block text-left text-xs">
              <p className="font-bold text-slate-900 leading-tight">
                {user?.full_name || 'Excise Officer'}
              </p>
              <p className="text-[11px] text-slate-500 font-medium">
                {user?.designation || 'Excise Sub-Inspector'}
              </p>
            </div>
            <button
              onClick={logout}
              title="Log Out of Session"
              className="p-1.5 text-slate-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors border border-transparent hover:border-red-200"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Interactive Logo Zoom Modal */}
      <LogoZoomModal
        isOpen={isLogoModalOpen}
        onClose={() => setIsLogoModalOpen(false)}
        src="/assets/andhra-pradesh-government-logo.jpg"
        alt="Government of Andhra Pradesh Official Emblem"
        title="Government of Andhra Pradesh"
        subtitle="Official State Emblem • Prohibition & Excise Department • FIR VisionAI"
      />
    </header>
  );
};

