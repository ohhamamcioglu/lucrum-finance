import { useState } from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Menu, X } from 'lucide-react';
import { useAuth } from '../AuthContext';
import { useT } from '../i18n';
import type { Language } from '../i18n';

interface PublicNavProps {
  lang: Language;
  onLangChange: (lang: Language) => void;
}

export default function PublicNav({ lang, onLangChange }: PublicNavProps) {
  const { token } = useAuth();
  const t = useT(lang);
  const [mobileOpen, setMobileOpen] = useState(false);

  const links = [
    { to: '/', label: t.navHome },
    { to: '/pricing', label: t.navPricing },
  ];

  return (
    <header className="sticky top-0 z-40 w-full bg-[#F9F7F2]/90 backdrop-blur-md border-b border-[#8C9A86]/10">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#8C9A86] flex items-center justify-center shadow-md shadow-[#8C9A86]/30">
            <TrendingUp className="w-4.5 h-4.5 text-white" />
          </div>
          <span className="text-lg font-black tracking-widest text-[#4A443F] font-serif">LUCRUM</span>
        </Link>

        <nav className="hidden md:flex items-center gap-8">
          {links.map((l) => (
            <Link key={l.to} to={l.to} className="text-xs font-bold uppercase tracking-wider text-[#6B645E] hover:text-[#4A443F] transition-colors">
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          <div className="flex gap-1">
            <button
              onClick={() => onLangChange('tr')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md border transition-all cursor-pointer ${
                lang === 'tr' ? 'bg-[#8C9A86] text-white border-[#8C9A86]' : 'text-[#4A443F] border-[#4A443F]/20 hover:bg-[#8C9A86]/10'
              }`}
            >
              TR
            </button>
            <button
              onClick={() => onLangChange('en')}
              className={`px-2.5 py-1 text-[10px] font-semibold rounded-md border transition-all cursor-pointer ${
                lang === 'en' ? 'bg-[#8C9A86] text-white border-[#8C9A86]' : 'text-[#4A443F] border-[#4A443F]/20 hover:bg-[#8C9A86]/10'
              }`}
            >
              EN
            </button>
          </div>

          {token ? (
            <Link to="/app" className="px-4 py-2 bg-[#8C9A86] hover:bg-[#7A8875] text-white text-xs font-bold uppercase tracking-wider rounded-xl shadow-md shadow-[#8C9A86]/20 transition-all">
              {t.navGoToApp}
            </Link>
          ) : (
            <>
              <Link to="/login" className="text-xs font-bold uppercase tracking-wider text-[#4A443F] hover:text-[#8C9A86] transition-colors">
                {t.navLogin}
              </Link>
              <Link to="/register" className="px-4 py-2 bg-[#8C9A86] hover:bg-[#7A8875] text-white text-xs font-bold uppercase tracking-wider rounded-xl shadow-md shadow-[#8C9A86]/20 transition-all">
                {t.navRegister}
              </Link>
            </>
          )}
        </div>

        <button className="md:hidden text-[#4A443F]" onClick={() => setMobileOpen((v) => !v)}>
          {mobileOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-[#8C9A86]/10 bg-[#F9F7F2] px-6 py-4 space-y-3">
          {links.map((l) => (
            <Link key={l.to} to={l.to} onClick={() => setMobileOpen(false)} className="block text-xs font-bold uppercase tracking-wider text-[#6B645E]">
              {l.label}
            </Link>
          ))}
          {token ? (
            <Link to="/app" onClick={() => setMobileOpen(false)} className="block text-xs font-bold uppercase tracking-wider text-[#8C9A86]">
              {t.navGoToApp}
            </Link>
          ) : (
            <>
              <Link to="/login" onClick={() => setMobileOpen(false)} className="block text-xs font-bold uppercase tracking-wider text-[#4A443F]">
                {t.navLogin}
              </Link>
              <Link to="/register" onClick={() => setMobileOpen(false)} className="block text-xs font-bold uppercase tracking-wider text-[#8C9A86]">
                {t.navRegister}
              </Link>
            </>
          )}
        </div>
      )}
    </header>
  );
}
