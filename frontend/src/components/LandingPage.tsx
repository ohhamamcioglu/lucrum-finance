import { useState } from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, ShieldCheck, BarChart3, Target } from 'lucide-react';
import PublicNav from './PublicNav';
import { useT } from '../i18n';
import type { Language } from '../i18n';
import { useAuth } from '../AuthContext';

export default function LandingPage() {
  const [lang, setLang] = useState<Language>('tr');
  const t = useT(lang);
  const { token } = useAuth();

  const features = [
    { icon: BarChart3, title: t.landingFeature1Title, desc: t.landingFeature1Desc },
    { icon: ShieldCheck, title: t.landingFeature2Title, desc: t.landingFeature2Desc },
    { icon: Target, title: t.landingFeature3Title, desc: t.landingFeature3Desc },
  ];

  return (
    <div className="min-h-screen bg-[#F9F7F2] font-sans text-[#4A443F]">
      <PublicNav lang={lang} onLangChange={setLang} />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute top-[-15%] left-[-10%] w-[500px] h-[500px] rounded-full bg-[#8C9A86]/20 blur-[120px] pointer-events-none" />
        <div className="absolute bottom-[-15%] right-[-10%] w-[500px] h-[500px] rounded-full bg-[#9E958C]/20 blur-[140px] pointer-events-none" />

        <div className="relative max-w-4xl mx-auto px-6 pt-24 pb-20 text-center">
          <div className="inline-flex items-center gap-2 mb-6 px-4 py-1.5 bg-[#8C9A86]/10 border border-[#8C9A86]/20 rounded-full">
            <TrendingUp className="w-3.5 h-3.5 text-[#8C9A86]" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C9A86]">LUCRUM</span>
          </div>

          <h1 className="text-4xl md:text-5xl font-black tracking-tight text-[#4A443F] leading-tight mb-6">
            {t.landingHeadline}
          </h1>
          <p className="text-base text-[#6B645E] max-w-2xl mx-auto mb-10 leading-relaxed">
            {t.landingSubhead}
          </p>

          <div className="flex items-center justify-center gap-4">
            <Link
              to={token ? '/app' : '/register'}
              className="px-6 py-3 bg-[#8C9A86] hover:bg-[#7A8875] text-white text-xs font-bold uppercase tracking-wider rounded-xl shadow-lg shadow-[#8C9A86]/20 transition-all"
            >
              {token ? t.navGoToApp : t.landingCtaPrimary}
            </Link>
            <Link
              to="/pricing"
              className="px-6 py-3 bg-white border border-[#8C9A86]/20 hover:border-[#8C9A86] text-[#4A443F] text-xs font-bold uppercase tracking-wider rounded-xl transition-all"
            >
              {t.landingCtaSecondary}
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 pb-24">
        <h2 className="text-xl font-bold text-center text-[#4A443F] mb-12">{t.landingFeaturesTitle}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {features.map((f) => (
            <div key={f.title} className="bg-white border border-[#8C9A86]/10 rounded-2xl p-6 shadow-sm">
              <div className="w-10 h-10 rounded-xl bg-[#8C9A86]/10 flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-[#8C9A86]" />
              </div>
              <h3 className="text-sm font-bold text-[#4A443F] mb-2">{f.title}</h3>
              <p className="text-xs text-[#6B645E] leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-[#8C9A86]/10 py-8">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4 text-[10px] text-[#9E958C]">
          <span>LUCRUM &copy; {new Date().getFullYear()} — {t.landingFooterRights}</span>
          <div className="flex gap-4">
            <Link to="/legal/kvkk" className="hover:text-[#4A443F]">KVKK</Link>
            <Link to="/legal/terms" className="hover:text-[#4A443F]">{t.legalTermsTitle}</Link>
            <Link to="/legal/privacy" className="hover:text-[#4A443F]">{t.legalPrivacyTitle}</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
