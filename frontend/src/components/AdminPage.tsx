import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Users, Search, ShieldCheck, TrendingUp, ChevronLeft, ChevronRight, Eye, X, FileClock } from 'lucide-react';
import { useT } from '../i18n';
import type { Language, Translations } from '../i18n';
import { api } from '../services/api';
import { formatCurrency } from '../utils';

type AdminUser = {
  id: number; email: string; name: string; subscription_tier: string; subscription_status: string;
  is_admin: boolean; is_active: boolean; email_verified: boolean; created_at: string;
};

type AuditLogEntry = {
  id: number; admin_user_id: number | null; admin_email: string | null;
  target_user_id: number | null; target_email: string | null;
  action: string; details: string | null; created_at: string;
};

const PAGE_SIZE = 20;
const TIERS = ['FREE', 'PRO', 'ENTERPRISE'];

function auditActionLabel(action: string, t: Translations): string {
  if (action === 'tier_change') return t.adminAuditActionTierChange;
  if (action === 'toggle_active') return t.adminAuditActionToggleActive;
  if (action === 'view_portfolio') return t.adminAuditActionViewPortfolio;
  return action;
}

export default function AdminPage() {
  const [lang, setLang] = useState<Language>('tr');
  const t = useT(lang);

  const [stats, setStats] = useState<{ total_users: number; active_users: number; verified_users: number; admin_users: number } | null>(null);
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [activeSection, setActiveSection] = useState<'users' | 'audit'>('users');

  const [auditItems, setAuditItems] = useState<AuditLogEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditLoading, setAuditLoading] = useState(true);

  const [portfolioModalUser, setPortfolioModalUser] = useState<AdminUser | null>(null);
  const [portfolioData, setPortfolioData] = useState<any>(null);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const auditTotalPages = Math.max(1, Math.ceil(auditTotal / PAGE_SIZE));

  const load = useCallback(async (targetPage: number, targetSearch: string) => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.adminListUsers(targetPage, PAGE_SIZE, targetSearch);
      setItems(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err?.message || 'Failed to load users.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.adminGetStats().then(setStats).catch((err) => {
      console.error('Failed to load admin stats:', err);
      setError(err?.message || 'Failed to load stats.');
    });
  }, []);

  useEffect(() => {
    load(page, search);
  }, [page, load]);

  // Debounce search
  useEffect(() => {
    const handle = setTimeout(() => {
      setPage(1);
      load(1, search);
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const loadAuditLog = useCallback(async (targetPage: number) => {
    try {
      setAuditLoading(true);
      const res = await api.adminGetAuditLog(targetPage, PAGE_SIZE);
      setAuditItems(res.items);
      setAuditTotal(res.total);
    } catch (err: any) {
      console.error('Failed to load audit log:', err);
      setError(err?.message || 'Failed to load audit log.');
    } finally {
      setAuditLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeSection === 'audit') loadAuditLog(auditPage);
  }, [activeSection, auditPage, loadAuditLog]);

  const openPortfolioModal = async (user: AdminUser) => {
    setPortfolioModalUser(user);
    setPortfolioData(null);
    setPortfolioError(null);
    setPortfolioLoading(true);
    try {
      const data = await api.adminGetUserPortfolio(user.id);
      setPortfolioData(data);
    } catch (err: any) {
      console.error('Failed to load user portfolio:', err);
      setPortfolioError(err?.message || t.adminPortfolioLoadFailed);
    } finally {
      setPortfolioLoading(false);
    }
  };

  const handleTierChange = async (userId: number, tier: string) => {
    try {
      setBusyId(userId);
      const updated = await api.adminUpdateUser(userId, { subscription_tier: tier });
      setItems((prev) => prev.map((u) => (u.id === userId ? { ...u, subscription_tier: updated.subscription_tier } : u)));
    } catch (err: any) {
      setError(err?.message || 'Update failed.');
    } finally {
      setBusyId(null);
    }
  };

  const handleToggleActive = async (user: AdminUser) => {
    try {
      setBusyId(user.id);
      const updated = await api.adminUpdateUser(user.id, { is_active: !user.is_active });
      setItems((prev) => prev.map((u) => (u.id === user.id ? { ...u, is_active: updated.is_active } : u)));
    } catch (err: any) {
      setError(err?.message || t.adminCannotDisableSelf);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9F7F2] font-sans text-[#4A443F]">
      <header className="sticky top-0 z-40 w-full bg-[#F9F7F2]/90 backdrop-blur-md border-b border-[#8C9A86]/10">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/app" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#8C9A86] flex items-center justify-center shadow-md shadow-[#8C9A86]/30">
              <TrendingUp className="w-4.5 h-4.5 text-white" />
            </div>
            <span className="text-lg font-black tracking-widest text-[#4A443F] font-serif">LUCRUM</span>
          </Link>
          <div className="flex gap-1">
            <button onClick={() => setLang('tr')} className={`px-2.5 py-1 text-[10px] font-semibold rounded-md border cursor-pointer ${lang === 'tr' ? 'bg-[#8C9A86] text-white border-[#8C9A86]' : 'text-[#4A443F] border-[#4A443F]/20'}`}>TR</button>
            <button onClick={() => setLang('en')} className={`px-2.5 py-1 text-[10px] font-semibold rounded-md border cursor-pointer ${lang === 'en' ? 'bg-[#8C9A86] text-white border-[#8C9A86]' : 'text-[#4A443F] border-[#4A443F]/20'}`}>EN</button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2 mb-8">
          <ShieldCheck className="w-5 h-5 text-[#8C9A86]" />
          <h1 className="text-xl font-bold text-[#4A443F]">{t.adminTitle}</h1>
        </div>

        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[
              { label: t.adminTotalUsers, value: stats.total_users },
              { label: t.adminActiveUsers, value: stats.active_users },
              { label: t.adminVerifiedUsers, value: stats.verified_users },
              { label: t.adminAdminUsers, value: stats.admin_users },
            ].map((s) => (
              <div key={s.label} className="bg-white border border-[#8C9A86]/10 rounded-xl p-4 shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1">{s.label}</p>
                <p className="text-2xl font-black text-[#4A443F]">{s.value}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveSection('users')}
            className={`flex items-center gap-1.5 px-3.5 py-2 text-[11px] font-bold uppercase tracking-wider rounded-lg cursor-pointer transition-all ${
              activeSection === 'users' ? 'bg-[#8C9A86] text-white' : 'bg-white border border-[#8C9A86]/10 text-[#6B645E] hover:text-[#4A443F]'
            }`}
          >
            <Users className="w-3.5 h-3.5" />{t.adminTabUsers}
          </button>
          <button
            onClick={() => setActiveSection('audit')}
            className={`flex items-center gap-1.5 px-3.5 py-2 text-[11px] font-bold uppercase tracking-wider rounded-lg cursor-pointer transition-all ${
              activeSection === 'audit' ? 'bg-[#8C9A86] text-white' : 'bg-white border border-[#8C9A86]/10 text-[#6B645E] hover:text-[#4A443F]'
            }`}
          >
            <FileClock className="w-3.5 h-3.5" />{t.adminTabAuditLog}
          </button>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-50 text-red-700 text-xs font-semibold rounded-xl">{error}</div>
        )}

        {activeSection === 'users' && (
        <div className="bg-white border border-[#8C9A86]/10 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-[#8C9A86]/10 flex items-center gap-2">
            <Users className="w-4 h-4 text-[#8C9A86]" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#4A443F]">{t.adminUsers}</span>
            <div className="relative ml-auto w-72 max-w-full">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9E958C]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t.adminSearch}
                className="w-full pl-9 pr-3 py-2 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-xs outline-none transition-all"
              />
            </div>
          </div>

          {/* Masaüstü: tam tablo. Mobilde bunun yerine aşağıdaki kart listesi gösterilir
              (dar ekranda 4 sütunlu tablo, içindeki select/buton kontrolleriyle birlikte
              yatay kaydırmayla bile kullanışsız oluyordu). */}
          <div className="overflow-x-auto hidden md:block">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-[#9E958C] border-b border-[#8C9A86]/10">
                  <th className="px-4 py-3">{t.adminEmail}</th>
                  <th className="px-4 py-3">{t.adminName}</th>
                  <th className="px-4 py-3">{t.adminTier}</th>
                  <th className="px-4 py-3">{t.adminStatus}</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9E958C]">…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9E958C]">{t.adminNoResults}</td></tr>
                ) : (
                  items.map((u) => (
                    <tr key={u.id} className="border-b border-[#8C9A86]/5 last:border-0">
                      <td className="px-4 py-3 font-medium text-[#4A443F]">
                        {u.email}
                        {u.is_admin && (
                          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#8C9A86]/10 text-[#8C9A86] text-[9px] font-bold uppercase">
                            <ShieldCheck className="w-2.5 h-2.5" /> {t.adminAdminBadge}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[#6B645E]">{u.name}</td>
                      <td className="px-4 py-3">
                        <select
                          value={u.subscription_tier}
                          disabled={busyId === u.id}
                          onChange={(e) => handleTierChange(u.id, e.target.value)}
                          className="bg-[#F2EDE4]/50 border border-[#8C9A86]/20 rounded-lg px-2 py-1 text-[10px] font-semibold outline-none cursor-pointer"
                        >
                          {TIERS.map((tier) => (
                            <option key={tier} value={tier}>{tier}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          disabled={busyId === u.id}
                          onClick={() => handleToggleActive(u)}
                          className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider cursor-pointer transition-all ${
                            u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
                          }`}
                        >
                          {u.is_active ? t.adminActive : t.adminDisabled}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => openPortfolioModal(u)}
                          title={t.adminViewPortfolio}
                          aria-label={t.adminViewPortfolio}
                          className="text-[#9E958C] hover:text-[#8C9A86] p-1.5 rounded hover:bg-[#8C9A86]/10 transition-all cursor-pointer"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobil: kart listesi — select/toggle kontrolleri bir dokunuş arkasına
              gizlenmiyor, admin işlemleri her zaman doğrudan erişilebilir kalıyor. */}
          <div className="md:hidden divide-y divide-[#8C9A86]/10">
            {loading ? (
              <div className="px-4 py-8 text-center text-[#9E958C] text-xs">…</div>
            ) : items.length === 0 ? (
              <div className="px-4 py-8 text-center text-[#9E958C] text-xs">{t.adminNoResults}</div>
            ) : (
              items.map((u) => (
                <div key={u.id} className="px-4 py-3 space-y-2">
                  <div className="font-medium text-[#4A443F] text-xs break-all">
                    {u.email}
                    {u.is_admin && (
                      <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#8C9A86]/10 text-[#8C9A86] text-[9px] font-bold uppercase">
                        <ShieldCheck className="w-2.5 h-2.5" /> {t.adminAdminBadge}
                      </span>
                    )}
                  </div>
                  <div className="text-[#6B645E] text-xs">{u.name}</div>
                  <div className="flex items-center gap-2">
                    <select
                      value={u.subscription_tier}
                      disabled={busyId === u.id}
                      onChange={(e) => handleTierChange(u.id, e.target.value)}
                      className="bg-[#F2EDE4]/50 border border-[#8C9A86]/20 rounded-lg px-2 py-1 text-[10px] font-semibold outline-none cursor-pointer"
                    >
                      {TIERS.map((tier) => (
                        <option key={tier} value={tier}>{tier}</option>
                      ))}
                    </select>
                    <button
                      disabled={busyId === u.id}
                      onClick={() => handleToggleActive(u)}
                      className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider cursor-pointer transition-all ${
                        u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {u.is_active ? t.adminActive : t.adminDisabled}
                    </button>
                    <button
                      onClick={() => openPortfolioModal(u)}
                      aria-label={t.adminViewPortfolio}
                      className="ml-auto text-[#9E958C] hover:text-[#8C9A86] p-1.5 rounded hover:bg-[#8C9A86]/10 transition-all cursor-pointer"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="px-4 py-3 border-t border-[#8C9A86]/10 flex items-center justify-between">
            <span className="text-[10px] text-[#9E958C] font-semibold">{t.adminPage(page, totalPages)}</span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#8C9A86]/20 text-[10px] font-bold uppercase tracking-wider text-[#4A443F] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft className="w-3 h-3" /> {t.adminPrev}
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#8C9A86]/20 text-[10px] font-bold uppercase tracking-wider text-[#4A443F] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                {t.adminNext} <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
        )}

        {activeSection === 'audit' && (
        <div className="bg-white border border-[#8C9A86]/10 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-[#8C9A86]/10 flex items-center gap-2">
            <FileClock className="w-4 h-4 text-[#8C9A86]" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#4A443F]">{t.adminTabAuditLog}</span>
          </div>

          {/* Masaüstü: tam tablo. Mobilde bunun yerine aşağıdaki kart listesi gösterilir. */}
          <div className="overflow-x-auto hidden md:block">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-[#9E958C] border-b border-[#8C9A86]/10">
                  <th className="px-4 py-3">{t.adminAuditDateCol}</th>
                  <th className="px-4 py-3">{t.adminAuditAdminCol}</th>
                  <th className="px-4 py-3">{t.adminAuditActionCol}</th>
                  <th className="px-4 py-3">{t.adminAuditTargetCol}</th>
                  <th className="px-4 py-3">{t.adminAuditDetailsCol}</th>
                </tr>
              </thead>
              <tbody>
                {auditLoading ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9E958C]">…</td></tr>
                ) : auditItems.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9E958C]">{t.adminAuditNoResults}</td></tr>
                ) : (
                  auditItems.map((e) => (
                    <tr key={e.id} className="border-b border-[#8C9A86]/5 last:border-0">
                      <td className="px-4 py-3 text-[#6B645E] font-mono whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3 text-[#4A443F]">{e.admin_email ?? '—'}</td>
                      <td className="px-4 py-3 text-[#4A443F] font-semibold">{auditActionLabel(e.action, t)}</td>
                      <td className="px-4 py-3 text-[#6B645E]">{e.target_email ?? '—'}</td>
                      <td className="px-4 py-3 text-[#6B645E]">{e.details ?? '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobil: kart listesi */}
          <div className="md:hidden divide-y divide-[#8C9A86]/10">
            {auditLoading ? (
              <div className="px-4 py-8 text-center text-[#9E958C] text-xs">…</div>
            ) : auditItems.length === 0 ? (
              <div className="px-4 py-8 text-center text-[#9E958C] text-xs">{t.adminAuditNoResults}</div>
            ) : (
              auditItems.map((e) => (
                <div key={e.id} className="px-4 py-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-[#4A443F] text-xs">{auditActionLabel(e.action, t)}</span>
                    <span className="text-[10px] text-[#9E958C] font-mono">{new Date(e.created_at).toLocaleString()}</span>
                  </div>
                  <div className="text-[11px] text-[#6B645E]">{t.adminAuditAdminCol}: {e.admin_email ?? '—'}</div>
                  <div className="text-[11px] text-[#6B645E]">{t.adminAuditTargetCol}: {e.target_email ?? '—'}</div>
                  {e.details && <div className="text-[11px] text-[#9E958C]">{e.details}</div>}
                </div>
              ))
            )}
          </div>

          <div className="px-4 py-3 border-t border-[#8C9A86]/10 flex items-center justify-between">
            <span className="text-[10px] text-[#9E958C] font-semibold">{t.adminPage(auditPage, auditTotalPages)}</span>
            <div className="flex gap-2">
              <button
                disabled={auditPage <= 1}
                onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#8C9A86]/20 text-[10px] font-bold uppercase tracking-wider text-[#4A443F] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft className="w-3 h-3" /> {t.adminPrev}
              </button>
              <button
                disabled={auditPage >= auditTotalPages}
                onClick={() => setAuditPage((p) => Math.min(auditTotalPages, p + 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#8C9A86]/20 text-[10px] font-bold uppercase tracking-wider text-[#4A443F] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                {t.adminNext} <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
        )}
      </div>

      {/* PORTFOLIO MODAL — salt okunur, destek amaçlı görüntüleme */}
      {portfolioModalUser && (
        <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4"
          onClick={() => setPortfolioModalUser(null)}>
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-[#F9F7F2] border border-[#8C9A86]/10 rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] overflow-hidden flex flex-col"
          >
            <div className="px-6 py-4 border-b border-[#8C9A86]/10 flex justify-between items-center bg-white">
              <div>
                <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest font-serif">{t.adminPortfolioModalTitle}</h3>
                <p className="text-[11px] text-[#6B645E] mt-0.5">{portfolioModalUser.email}</p>
              </div>
              <button onClick={() => setPortfolioModalUser(null)} aria-label={t.adminPortfolioClose}
                className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto space-y-4">
              {portfolioLoading ? (
                <div className="text-center py-8 text-[#9E958C] text-xs">…</div>
              ) : portfolioError ? (
                <div className="text-center py-8 text-red-600 text-xs font-semibold">{portfolioError}</div>
              ) : portfolioData ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-white border border-[#8C9A86]/10 rounded-xl p-3">
                      <p className="text-[9px] font-bold uppercase tracking-wider text-[#9E958C] mb-1">{t.adminPortfolioTotalValue}</p>
                      <p className="text-lg font-black text-[#4A443F] font-mono">{formatCurrency(portfolioData.totalValue ?? 0, 'TRY')}</p>
                    </div>
                    <div className="bg-white border border-[#8C9A86]/10 rounded-xl p-3">
                      <p className="text-[9px] font-bold uppercase tracking-wider text-[#9E958C] mb-1">{t.adminPortfolioHoldingsCount}</p>
                      <p className="text-lg font-black text-[#4A443F] font-mono">{(portfolioData.holdings ?? []).length}</p>
                    </div>
                  </div>
                  {(portfolioData.holdings ?? []).length === 0 ? (
                    <p className="text-xs text-[#9E958C] text-center py-4">{t.adminPortfolioNoHoldings}</p>
                  ) : (
                    <div className="divide-y divide-[#8C9A86]/10 border border-[#8C9A86]/10 rounded-xl overflow-hidden">
                      {(portfolioData.holdings ?? []).map((h: any, idx: number) => (
                        <div key={h.id ?? h.symbol ?? idx} className="px-3 py-2 flex items-center justify-between bg-white">
                          <div>
                            <p className="text-xs font-semibold text-[#4A443F]">{h.symbol}</p>
                            <p className="text-[10px] text-[#9E958C]">{h.assetClass}</p>
                          </div>
                          <p className="text-xs font-mono font-bold text-[#4A443F]">{formatCurrency(h.value ?? 0, 'TRY')}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
