import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Users, Search, ShieldCheck, TrendingUp, ChevronLeft, ChevronRight } from 'lucide-react';
import { useT } from '../i18n';
import type { Language } from '../i18n';
import { api } from '../services/api';

type AdminUser = {
  id: number; email: string; name: string; subscription_tier: string; subscription_status: string;
  is_admin: boolean; is_active: boolean; email_verified: boolean; created_at: string;
};

const PAGE_SIZE = 20;
const TIERS = ['FREE', 'PRO', 'ENTERPRISE'];

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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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
    api.adminGetStats().then(setStats).catch(() => {});
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

          {error && (
            <div className="px-4 py-3 bg-red-50 text-red-700 text-xs font-semibold">{error}</div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-[#9E958C] border-b border-[#8C9A86]/10">
                  <th className="px-4 py-3">{t.adminEmail}</th>
                  <th className="px-4 py-3">{t.adminName}</th>
                  <th className="px-4 py-3">{t.adminTier}</th>
                  <th className="px-4 py-3">{t.adminStatus}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-[#9E958C]">…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-[#9E958C]">{t.adminNoResults}</td></tr>
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
                    </tr>
                  ))
                )}
              </tbody>
            </table>
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
      </div>
    </div>
  );
}
