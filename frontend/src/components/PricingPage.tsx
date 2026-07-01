import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Crown, Sparkles, CheckCircle } from 'lucide-react';
import PublicNav from './PublicNav';
import { useT } from '../i18n';
import type { Language } from '../i18n';
import { useAuth } from '../AuthContext';
import { api } from '../services/api';

const PLANS = [
  { id: 'FREE', title: 'Free', price: '$0', limitPos: '5', limitAlert: '3' },
  { id: 'PRO', title: 'Pro', price: '$19', limitPos: '50', limitAlert: '20' },
  { id: 'ENTERPRISE', title: 'Enterprise', price: '$99', limitPos: null, limitAlert: null },
];

export default function PricingPage() {
  const [lang, setLang] = useState<Language>('tr');
  const t = useT(lang);
  const { token } = useAuth();
  const navigate = useNavigate();

  const [currentTier, setCurrentTier] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.getUserProfile().then((p) => setCurrentTier(p.subscription_tier)).catch(() => {});
  }, [token]);

  const handleSelect = async (planId: string) => {
    if (!token) {
      navigate('/register');
      return;
    }
    try {
      setLoadingId(planId);
      const res = await api.subscribeToPlan(planId);
      setCurrentTier(res.subscription_tier);
      setToast(t.pricingUpgradeSuccess);
    } catch {
      setToast(t.pricingUpgradeFailed);
    } finally {
      setLoadingId(null);
      setTimeout(() => setToast(null), 3000);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9F7F2] font-sans text-[#4A443F]">
      <PublicNav lang={lang} onLangChange={setLang} />

      <div className="max-w-5xl mx-auto px-6 py-20">
        <div className="text-center mb-14">
          <h1 className="text-3xl font-black text-[#4A443F] mb-3">{t.pricingTitle}</h1>
          <p className="text-sm text-[#6B645E]">{t.pricingSubtitle}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((p) => {
            const isCurrent = token && currentTier === p.id;
            return (
              <div
                key={p.id}
                className={`bg-white rounded-2xl p-7 border transition-all flex flex-col ${
                  p.id === 'PRO' ? 'border-[#8C9A86] shadow-xl shadow-[#8C9A86]/10 scale-[1.02]' : 'border-[#8C9A86]/15 shadow-sm'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  {p.id === 'FREE' && <Crown className="w-4 h-4 text-slate-500" />}
                  {p.id === 'PRO' && <Crown className="w-4 h-4 text-amber-500" />}
                  {p.id === 'ENTERPRISE' && <Sparkles className="w-4 h-4 text-teal-500" />}
                  <span className="text-sm font-bold text-[#4A443F]">{p.title}</span>
                </div>
                <div className="flex items-baseline gap-1 mb-6">
                  <span className="text-3xl font-black text-[#4A443F]">{p.price}</span>
                  <span className="text-xs text-[#9E958C]">{t.pricingPerMonth}</span>
                </div>

                <ul className="space-y-3 text-xs text-[#6B645E] mb-8 flex-1">
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-3.5 h-3.5 text-[#8C9A86] shrink-0" />
                    <span>{t.pricingPositions}: <strong className="text-[#4A443F]">{p.limitPos ?? t.pricingUnlimited}</strong></span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle className="w-3.5 h-3.5 text-[#8C9A86] shrink-0" />
                    <span>{t.pricingAlerts}: <strong className="text-[#4A443F]">{p.limitAlert ?? t.pricingUnlimited}</strong></span>
                  </li>
                </ul>

                <button
                  disabled={!!isCurrent || loadingId === p.id}
                  onClick={() => handleSelect(p.id)}
                  className={`w-full py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
                    isCurrent
                      ? 'bg-[#8C9A86]/20 text-[#8C9A86] cursor-not-allowed'
                      : 'bg-[#8C9A86] hover:bg-[#7A8875] text-white'
                  }`}
                >
                  {isCurrent ? t.pricingCurrentPlan : token ? t.pricingSelect : t.pricingSignUpFirst}
                </button>
              </div>
            );
          })}
        </div>

        <div className="text-center mt-10 text-[10px] text-[#9E958C]">
          <Link to="/legal/terms" className="hover:text-[#4A443F] underline">{t.legalTermsTitle}</Link>
        </div>
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 bg-[#4A443F] text-white rounded-xl px-5 py-3 shadow-2xl z-50 text-sm font-semibold">
          {toast}
        </div>
      )}
    </div>
  );
}
