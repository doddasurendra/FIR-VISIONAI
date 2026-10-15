import React from 'react';
import { ShieldCheck, Lock, ExternalLink, Activity } from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';
import { useAuth } from '../../context/AuthContext';

export const GovernmentFooter: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();

  return (
    <footer className="bg-slate-900 text-slate-400 border-t border-slate-800 text-xs mt-auto">
      {/* Top Banner of Footer */}
      <div className="max-w-[1700px] mx-auto px-4 sm:px-6 py-6 grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Col 1: Portal Identification */}
        <div className="space-y-2 md:col-span-2">
          <div className="flex items-center space-x-2">
            <div className="w-5 h-5 rounded bg-amber-400 flex items-center justify-center text-slate-950 font-black text-[10px]">
              AP
            </div>
            <h4 className="font-bold text-slate-200 uppercase tracking-wide">
              Andhra Pradesh Prohibition & Excise Department
            </h4>
          </div>
          <p className="text-slate-400 leading-relaxed text-[11px] max-w-xl">
            FIR Sahayak is an official AI-assisted Unified First Information Report (u-FIR) intelligence
            and case workflow platform. Built with strict PDF-grounded RAG verification, tamper-evident
            cryptographic audit chains, and multi-tier departmental jurisdiction scoping.
          </p>
          <div className="flex items-center space-x-3 text-[11px] text-slate-400 pt-1">
            <span className="flex items-center space-x-1 text-emerald-400">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>SHA-256 Recursive Audit Chain Active</span>
            </span>
            <span>&bull;</span>
            <span className="flex items-center space-x-1 text-sky-400">
              <Lock className="w-3.5 h-3.5" />
              <span>AES-256 Document Encryption</span>
            </span>
          </div>
        </div>

        {/* Col 2: Statutory Compliance */}
        <div className="space-y-1.5">
          <h5 className="font-semibold text-slate-300 uppercase tracking-wider text-[11px]">
            Statutory Regimes
          </h5>
          <ul className="space-y-1 text-[11px]">
            <li>&bull; Andhra Pradesh Excise Act, 1968</li>
            <li>&bull; Narcotic Drugs & Psychotropic Substances Act, 1985</li>
            <li>&bull; Section 172 CrPC / Bharatiya Nagarik Suraksha Sanhita (BNSS)</li>
            <li>&bull; Bharatiya Nyaya Sanhita (BNS, 2023)</li>
          </ul>
        </div>

        {/* Col 3: Active Session Scope */}
        <div className="space-y-1.5">
          <h5 className="font-semibold text-slate-300 uppercase tracking-wider text-[11px]">
            Session Security & Scope
          </h5>
          <div className="bg-slate-800/80 p-2.5 rounded border border-slate-700 space-y-1 text-[11px]">
            <div className="flex justify-between">
              <span className="text-slate-400">Officer:</span>
              <span className="text-slate-200 font-medium">{user?.full_name || 'Excise Officer'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Scope Level:</span>
              <span className="text-amber-400 font-bold">{user?.role || 'STATION'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Jurisdiction:</span>
              <span className="text-slate-200 font-medium truncate max-w-[140px]">
                {user?.station || user?.district || 'Andhra Pradesh'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Copyright & Disclaimer */}
      <div className="bg-slate-950 py-3 border-t border-slate-800/80">
        <div className="max-w-[1700px] mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 gap-2">
          <div>
            &copy; {new Date().getFullYear()} Government of Andhra Pradesh. All rights reserved.
            Prohibition & Excise Department.
          </div>
          <div className="flex items-center space-x-4">
            <span>Confidential &bull; Authorized Departmental Use Only</span>
            <span>v2.0-cloud-ready</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
