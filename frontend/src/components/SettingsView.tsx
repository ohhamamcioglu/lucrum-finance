import { useState, FormEvent, useEffect } from 'react';
import { Shield, User, Landmark, CheckCircle, Globe, CreditCard, Sparkles, Crown } from 'lucide-react';
import { UserSettings } from '../types';
import { useT } from '../i18n';
import type { Language } from '../i18n';
import { api } from '../services/api';
import { useCheckout } from '../hooks/useCheckout';

interface SettingsViewProps {
  settings: UserSettings;
  onUpdateSettings: (newSettings: Partial<UserSettings>) => void;
  onResetPortfolio: () => void;
  onLogout: () => void;
  currentPositionCount: number;
  onError?: (message: string) => void;
}

export default function SettingsView({ settings, onUpdateSettings, onResetPortfolio, onLogout, currentPositionCount, onError }: SettingsViewProps) {
  const t = useT(settings.language);
  const [userName, setUserName] = useState(settings.userName);
  const [userRole, setUserRole] = useState(settings.userRole);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  
  const [profile, setProfile] = useState<any>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [showToast, setShowToast] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const checkout = useCheckout();

  const [paymentHistory, setPaymentHistory] = useState<Awaited<ReturnType<typeof api.getPaymentHistory>>>([]);
  const [loadingPayments, setLoadingPayments] = useState(true);

  useEffect(() => {
    loadProfile();
    api.getPaymentHistory()
      .then(setPaymentHistory)
      .catch((err) => {
        console.error('Failed to load payment history:', err);
        onError?.(t.profileLoadFailed);
      })
      .finally(() => setLoadingPayments(false));
  }, []);

  useEffect(() => {
    if (checkout.error) {
      setToastMessage(checkout.error);
      setShowToast(true);
      setTimeout(() => setShowToast(false), 4000);
    }
  }, [checkout.error]);

  const loadProfile = async () => {
    try {
      setLoadingProfile(true);
      const data = await api.getUserProfile();
      setProfile(data);
    } catch (err) {
      console.error("Failed to load user profile:", err);
      onError?.(t.profileLoadFailed);
    } finally {
      setLoadingProfile(false);
    }
  };

  const handleDowngradeToFree = async () => {
    try {
      setLoadingProfile(true);
      const res = await api.subscribeToPlan('FREE');
      setToastMessage(settings.language === 'tr' ? res.message : `Successfully switched to FREE!`);
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
      await loadProfile();
    } catch (err: any) {
      setToastMessage(settings.language === 'tr' ? "Plan değişikliği başarısız." : "Plan change failed.");
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
      setLoadingProfile(false);
    }
  };

  const handleProfileSave = (e: FormEvent) => {
    e.preventDefault();
    onUpdateSettings({ userName, userRole });
    setToastMessage(t.saveSuccess);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 2000);
  };

  return (
    <div className="space-y-6 select-none">

      <div>
        <h2 className="text-xl font-bold text-[#2D2926]">{t.settingsTitle}</h2>
        <p className="text-xs text-[#6B645E] mt-0.5">{t.settingsSubtitle}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

        {/* LEFT COLUMN */}
        <div className="lg:col-span-2 space-y-6">

          {/* Calibration Card */}
          <div id="settings-preferences-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm">
            <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-4">
              <Landmark className="w-4 h-4 text-[#8C9A86]" />
              {t.calibration}
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                  {t.baseCurrencyLabel}
                </label>
                <select
                  id="settings-select-currency"
                  value={settings.baseCurrency}
                  onChange={(e) => onUpdateSettings({ baseCurrency: e.target.value as any })}
                  className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs font-semibold text-[#2D2926] rounded-lg py-2 px-3 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86]"
                >
                  <option value="USD">USD ($) US Dollar</option>
                  <option value="EUR">EUR (€) Euro</option>
                  <option value="TRY">TRY (₺) Turkish Lira</option>
                  <option value="GBP">GBP (£) British Pound</option>
                </select>
                <span className="text-[10px] text-[#9E958C] block mt-1.5 leading-relaxed">
                  {t.baseCurrencyDesc}
                </span>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                  {t.benchmarkLabel}
                </label>
                <select
                  id="settings-select-benchmark"
                  value={settings.benchmark}
                  onChange={(e) => onUpdateSettings({ benchmark: e.target.value as any })}
                  className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs font-semibold text-[#2D2926] rounded-lg py-2 px-3 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86]"
                >
                  <option value="S&P 500">S&P 500 Index</option>
                  <option value="Nasdaq">Nasdaq Composite</option>
                  <option value="Bitcoin">Bitcoin Base Asset</option>
                  <option value="Gold">Gold Spot price</option>
                  <option value="BIST100">BIST 100 (Turkey)</option>
                  <option value="DAX">DAX (Germany)</option>
                  <option value="FTSE 100">FTSE 100 (UK)</option>
                  <option value="CAC 40">CAC 40 (France)</option>
                  <option value="Euro Stoxx">Euro Stoxx 50</option>
                </select>
                <span className="text-[10px] text-[#9E958C] block mt-1.5 leading-relaxed">
                  {t.benchmarkDesc}
                </span>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                  {t.riskToleranceLabel}
                </label>
                <select
                  id="settings-select-risktol"
                  value={settings.riskTolerance}
                  onChange={(e) => onUpdateSettings({ riskTolerance: e.target.value as any })}
                  className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs font-semibold text-[#2D2926] rounded-lg py-2 px-3 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86]"
                >
                  <option value="Conservative">{t.conservative}</option>
                  <option value="Balanced">{t.balanced}</option>
                  <option value="Aggressive">{t.aggressive}</option>
                </select>
                <span className="text-[10px] text-[#9E958C] block mt-1.5 leading-relaxed">
                  {t.riskToleranceDesc}
                </span>
              </div>
            </div>

            {/* Language Selector */}
            <div className="mt-6 pt-5 border-t border-[#E8E2D9]">
              <h4 className="font-sans text-xs font-bold text-[#2D2926] flex items-center gap-2 mb-4">
                <Globe className="w-3.5 h-3.5 text-[#8C9A86]" />
                {t.languageLabel}
              </h4>
              <div className="flex gap-2">
                {(['tr', 'en'] as Language[]).map((lang) => (
                  <button
                    key={lang}
                    id={`settings-lang-${lang}`}
                    onClick={() => onUpdateSettings({ language: lang })}
                    className={`flex-1 py-2.5 rounded-lg border text-xs font-bold uppercase tracking-widest transition-all ${
                      settings.language === lang
                        ? 'bg-[#8C9A86] text-white border-[#8C9A86] shadow-sm'
                        : 'bg-[#F1EFE9] text-[#6B645E] border-[#E8E2D9] hover:text-[#2D2926] hover:bg-[#E8E2D9]'
                    }`}
                  >
                    {lang === 'tr' ? 'Türkçe' : 'English'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Profile Card */}
          <div id="settings-profile-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm">
            <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-4">
              <User className="w-4 h-4 text-[#7A8874]" />
              {t.profileCard}
            </h3>

            <form onSubmit={handleProfileSave} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                    {t.operatorUsername}
                  </label>
                  <input
                    id="settings-username-input"
                    type="text" required
                    value={userName}
                    onChange={(e) => setUserName(e.target.value)}
                    className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs text-[#2D2926] rounded-lg py-2 px-3 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86] font-medium"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                    {t.authorityTier}
                  </label>
                  <input
                    id="settings-role-input"
                    type="text" required
                    value={userRole}
                    onChange={(e) => setUserRole(e.target.value)}
                    className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs text-[#2D2926] rounded-lg py-2 px-3 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86] font-medium"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  id="settings-save-profile-btn"
                  type="submit"
                  className="bg-[#8C9A86] hover:bg-[#7A8874] text-white font-bold text-xs px-5 py-2 rounded-full uppercase tracking-widest transition-all shadow-sm"
                >
                  {t.saveProfile}
                </button>
              </div>
            </form>
          </div>

          {/* SaaS Subscription Card */}
          <div id="settings-saas-plans-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[#8C9A86]" />
                {settings.language === 'tr' ? 'SaaS Üyelik Planı & Sınırları' : 'SaaS Subscription Plan & Limits'}
              </h3>
              {profile && (
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full flex items-center gap-1 ${
                  profile.subscription_tier === 'FREE' ? 'bg-slate-100 text-slate-700' :
                  profile.subscription_tier === 'PRO' ? 'bg-amber-100 text-amber-800 border border-amber-200' :
                  'bg-teal-100 text-teal-800 border border-teal-200'
                }`}>
                  {profile.subscription_tier === 'FREE' ? <Crown className="w-3 h-3" /> :
                   profile.subscription_tier === 'PRO' ? <Crown className="w-3 h-3 text-amber-500" /> :
                   <Sparkles className="w-3 h-3 text-teal-500" />}
                  {profile.subscription_tier}
                </span>
              )}
            </div>

            {loadingProfile ? (
              <div className="flex justify-center py-4">
                <div className="w-5 h-5 border-2 border-[#8C9A86] border-t-transparent rounded-full animate-spin"></div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Plans Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {[
                    { id: 'FREE', title: 'Free', price: '0$', limitPos: '5', limitPosNum: 5, limitAlert: '3' },
                    { id: 'PRO', title: 'Pro', price: '19$', limitPos: '50', limitPosNum: 50, limitAlert: '20' },
                    { id: 'ENTERPRISE', title: 'Enterprise', price: '99$', limitPos: t.planUnlimited, limitPosNum: null, limitAlert: t.planUnlimited }
                  ].map((p) => {
                    const isCurrent = profile?.subscription_tier === p.id;
                    const isOverLimit = isCurrent && p.limitPosNum !== null && currentPositionCount > p.limitPosNum;
                    return (
                      <div key={p.id} className={`p-4 rounded-xl border transition-all flex flex-col justify-between ${
                        isCurrent
                          ? 'border-[#8C9A86] bg-[#8C9A86]/5 shadow-sm'
                          : 'border-[#E8E2D9] hover:border-[#8C9A86]/50 bg-[#F9F7F2]/40'
                      }`}>
                        <div>
                          <div className="flex justify-between items-start">
                            <span className="text-xs font-bold text-[#2D2926]">{p.title}</span>
                            <span className="text-[10px] font-bold text-[#6B645E]">{p.price} {t.planPerMonth}</span>
                          </div>
                          <div className="mt-3 space-y-1.5 text-[10px] text-[#6B645E] font-medium">
                            <div className="flex justify-between items-center">
                              <span>{t.planPositions}</span>
                              {isCurrent ? (
                                <span className={`font-bold ${isOverLimit ? 'text-[#B5836F]' : 'text-[#2D2926]'}`}>
                                  {currentPositionCount} / {p.limitPos}
                                </span>
                              ) : (
                                <span className="font-bold text-[#2D2926]">{p.limitPos}</span>
                              )}
                            </div>
                            {isOverLimit && (
                              <div className="text-[9px] text-[#B5836F] font-semibold leading-relaxed pt-0.5">
                                {settings.language === 'tr'
                                  ? `Sınırı aştınız (${currentPositionCount}/${p.limitPos}) — yeni pozisyon eklemek için yükseltin.`
                                  : `Over limit (${currentPositionCount}/${p.limitPos}) — upgrade to add new positions.`}
                              </div>
                            )}
                            <div className="flex justify-between">
                              <span>{t.planPriceAlert}</span>
                              <span className="font-bold text-[#2D2926]">{p.limitAlert}</span>
                            </div>
                          </div>
                        </div>

                        {isCurrent ? (
                          <button
                            disabled
                            className="w-full mt-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#8C9A86]/20 text-[#8C9A86] cursor-not-allowed"
                          >
                            {t.planActive}
                          </button>
                        ) : p.id === 'FREE' ? (
                          <button
                            onClick={handleDowngradeToFree}
                            className="w-full mt-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#8C9A86] hover:bg-[#7A8874] text-white cursor-pointer"
                          >
                            {t.planSelect}
                          </button>
                        ) : (
                          <button
                            disabled={checkout.submitting}
                            onClick={() => checkout.startCheckout(p.id)}
                            className="w-full mt-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#8C9A86] hover:bg-[#7A8874] disabled:bg-[#8C9A86]/60 text-white cursor-pointer"
                          >
                            {t.checkoutBtn}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>

                {profile?.subscription_ends_at && profile.subscription_tier !== 'FREE' && (
                  <p className="text-[10px] text-[#9E958C] text-center font-medium italic">
                    {settings.language === 'tr'
                      ? `Aboneliğiniz ${new Date(profile.subscription_ends_at).toLocaleDateString()} tarihine kadar geçerlidir.`
                      : `Your subscription is active until ${new Date(profile.subscription_ends_at).toLocaleDateString()}.`}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Payment History Card */}
          <div id="settings-payment-history-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm space-y-4">
            <div>
              <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[#8C9A86]" />
                {t.paymentHistory}
              </h3>
              <p className="text-xs text-[#6B645E] font-medium mt-0.5">{t.paymentHistoryDesc}</p>
            </div>

            {loadingPayments ? (
              <div className="flex justify-center py-4">
                <div className="w-5 h-5 border-2 border-[#8C9A86] border-t-transparent rounded-full animate-spin"></div>
              </div>
            ) : paymentHistory.length === 0 ? (
              <p className="text-xs text-[#9E958C] text-center py-4 font-medium">{t.paymentHistoryEmpty}</p>
            ) : (
              <>
                {/* Masaüstü: tam tablo. Mobilde bunun yerine aşağıdaki kart listesi gösterilir
                    (dar ekranda 4 sütunlu tablo yatay kaydırmayla bile okunaksız oluyordu). */}
                <div className="overflow-x-auto hidden md:block">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#F1EFE9] border-b border-[#E8E2D9] text-[10px] font-bold uppercase tracking-wider text-[#6B645E]">
                        <th className="px-3 py-2">{t.paymentHistoryDate}</th>
                        <th className="px-3 py-2">{t.paymentHistoryPlan}</th>
                        <th className="px-3 py-2 text-right">{t.paymentHistoryAmount}</th>
                        <th className="px-3 py-2 text-right">{t.paymentHistoryStatus}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E8E2D9]/40">
                      {paymentHistory.map(p => (
                        <tr key={p.id}>
                          <td className="px-3 py-2 text-xs text-[#2D2926] font-mono">{new Date(p.created_at).toLocaleDateString()}</td>
                          <td className="px-3 py-2 text-xs text-[#2D2926] font-semibold">{p.plan_tier}</td>
                          <td className="px-3 py-2 text-xs text-right font-mono font-bold text-[#2D2926]">{p.amount} {p.currency}</td>
                          <td className="px-3 py-2 text-right">
                            <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                              p.status === 'completed' ? 'bg-[#8C9A86]/15 text-[#7A8874]' :
                              p.status === 'pending' ? 'bg-amber-100 text-amber-800' :
                              p.status === 'refunded' ? 'bg-slate-100 text-slate-700' :
                              'bg-[#B5836F]/15 text-[#B5836F]'
                            }`}>
                              {p.status === 'completed' ? t.paymentStatusCompleted :
                               p.status === 'pending' ? t.paymentStatusPending :
                               p.status === 'refunded' ? t.paymentStatusRefunded :
                               t.paymentStatusFailed}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobil: kart listesi */}
                <div className="md:hidden divide-y divide-[#E8E2D9]/60">
                  {paymentHistory.map(p => (
                    <div key={p.id} className="py-3 flex items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-[#2D2926]">{p.plan_tier}</div>
                        <div className="text-[10px] text-[#9E958C] font-mono mt-0.5">{new Date(p.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="text-right shrink-0 space-y-1">
                        <div className="text-xs font-mono font-bold text-[#2D2926]">{p.amount} {p.currency}</div>
                        <span className={`inline-block text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                          p.status === 'completed' ? 'bg-[#8C9A86]/15 text-[#7A8874]' :
                          p.status === 'pending' ? 'bg-amber-100 text-amber-800' :
                          p.status === 'refunded' ? 'bg-slate-100 text-slate-700' :
                          'bg-[#B5836F]/15 text-[#B5836F]'
                        }`}>
                          {p.status === 'completed' ? t.paymentStatusCompleted :
                           p.status === 'pending' ? t.paymentStatusPending :
                           p.status === 'refunded' ? t.paymentStatusRefunded :
                           t.paymentStatusFailed}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

        </div>

        {/* RIGHT COLUMN */}
        <div className="lg:col-span-1 space-y-6">

          {/* Compliance Card */}
          <div className="bg-white border border-[#E8E2D9] p-5 rounded-2xl shadow-sm space-y-3">
            <h3 className="font-sans text-xs font-bold text-[#2D2926] uppercase tracking-wider flex items-center gap-2">
              <Shield className="w-4 h-4 text-[#B5836F]" />
              {t.complianceCard}
            </h3>
            <p className="text-[11px] text-[#6B645E] leading-relaxed font-medium">
              {t.complianceText}
            </p>
          </div>

          {/* Danger Zone */}
          <div id="settings-danger-zone-card" className="bg-white border border-red-300/40 p-5 rounded-2xl shadow-sm space-y-3">
            <h3 className="font-sans text-xs font-bold text-red-500 uppercase tracking-wider">
              {t.dangerZone}
            </h3>
            <p className="text-[11px] text-[#6B645E] leading-relaxed font-medium">
              {t.dangerText}
            </p>

            {showResetConfirm ? (
              <div className="space-y-2.5 pt-1">
                <div className="text-[10px] text-[#B5836F] font-bold uppercase">
                  {t.confirmDeletion}
                </div>
                <div className="flex gap-2">
                  <button
                    id="confirm-reset-btn"
                    onClick={() => { onResetPortfolio(); setShowResetConfirm(false); }}
                    className="flex-1 bg-red-500 hover:bg-red-600 text-white font-bold text-[10px] py-1.5 rounded-full uppercase tracking-wider transition-all"
                  >
                    {t.confirmReset}
                  </button>
                  <button
                    id="cancel-reset-btn"
                    onClick={() => setShowResetConfirm(false)}
                    className="flex-1 bg-[#F1EFE9] border border-[#E8E2D9] text-[#6B645E] font-bold text-[10px] py-1.5 rounded-full uppercase tracking-wider transition-all hover:bg-[#E8E2D9]"
                  >
                    {t.cancelReset}
                  </button>
                </div>
              </div>
            ) : (
              <button
                id="initiate-reset-btn"
                onClick={() => setShowResetConfirm(true)}
                className="w-full bg-[#F9F7F2] hover:bg-red-50 border border-red-300/50 text-red-500 font-bold text-xs py-2 rounded-full transition-all cursor-pointer"
              >
                {t.initiateReset}
              </button>
            )}
          </div>

          {/* Log Out Card */}
          <div className="bg-white border border-[#E8E2D9] p-5 rounded-2xl shadow-sm space-y-3">
            <h3 className="font-sans text-xs font-bold text-[#2D2926] uppercase tracking-wider">
              {settings.language === 'tr' ? 'Oturumu Kapat' : 'Log Out'}
            </h3>
            <p className="text-[11px] text-[#6B645E] leading-relaxed font-medium">
              {settings.language === 'tr' 
                ? 'Bu cihazdaki oturumunuzu sonlandırır ve giriş ekranına yönlendirir.' 
                : 'Ends your session on this device and redirects to the login screen.'}
            </p>
            <button
              onClick={onLogout}
              className="w-full bg-[#8C9A86] hover:bg-[#7A8874] text-white font-bold text-xs py-2 rounded-full transition-all cursor-pointer text-center"
            >
              {settings.language === 'tr' ? 'Güvenli Çıkış Yap' : 'Secure Log Out'}
            </button>
          </div>

        </div>
      </div>

      {/* TOAST */}
      {showToast && (
        <div id="settings-success-toast" className="fixed bottom-6 right-6 bg-[#7A8874] text-white border border-[#8C9A86] rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3 z-50 font-bold text-sm">
          <CheckCircle className="w-4 h-4" />
          <span>{toastMessage}</span>
        </div>
      )}

    </div>
  );
}
