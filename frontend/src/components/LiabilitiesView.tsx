import { useState, FormEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Pencil, Trash2, X, Landmark, ChevronDown } from 'lucide-react';
import { Liability, LiabilityType, UserSettings } from '../types';
import { formatCurrency, convertCurrency } from '../utils';
import { useT } from '../i18n';
import ConfirmDialog from './ConfirmDialog';

interface LiabilitiesViewProps {
  liabilities: Liability[];
  settings: UserSettings;
  exchangeRates: { usd_rate: number; eur_rate: number; gbp_rate?: number };
  onAddLiability: (item: Omit<Liability, 'id'>) => Promise<void>;
  onEditLiability: (id: number, item: Omit<Liability, 'id'>) => Promise<void>;
  onDeleteLiability: (id: number) => Promise<void>;
}

const LIABILITY_TYPES: LiabilityType[] = ['Loan', 'CreditCard', 'Mortgage', 'Other'];

const emptyForm = (): Omit<Liability, 'id'> => ({
  name: '',
  liability_type: 'Loan',
  amount: 0,
  currency: 'TRY',
  due_date: null,
  interest_rate: null,
});

export default function LiabilitiesView({
  liabilities, settings, exchangeRates, onAddLiability, onEditLiability, onDeleteLiability,
}: LiabilitiesViewProps) {
  const t = useT(settings.language);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<Omit<Liability, 'id'>>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [expandedMobileRow, setExpandedMobileRow] = useState<number | null>(null);

  const typeLabel = (type: string) => {
    switch (type) {
      case 'Loan': return t.liabilityTypeLoan;
      case 'CreditCard': return t.liabilityTypeCreditCard;
      case 'Mortgage': return t.liabilityTypeMortgage;
      default: return t.liabilityTypeOther;
    }
  };

  const totalLiabilitiesBase = liabilities.reduce(
    (sum, l) => sum + convertCurrency(l.amount, l.currency, settings.baseCurrency, exchangeRates),
    0
  );

  const openAdd = () => {
    setEditingId(null);
    setForm(emptyForm());
    setShowModal(true);
  };

  const openEdit = (l: Liability) => {
    setEditingId(l.id);
    setForm({
      name: l.name,
      liability_type: l.liability_type,
      amount: l.amount,
      currency: l.currency,
      due_date: l.due_date ?? null,
      interest_rate: l.interest_rate ?? null,
    });
    setShowModal(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      if (editingId != null) {
        await onEditLiability(editingId, form);
      } else {
        await onAddLiability(form);
      }
      setShowModal(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* HERO */}
      <section className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="relative z-10">
          <h2 className="font-serif text-[12px] font-bold text-[#9E958C] uppercase tracking-widest mb-1.5">{t.totalLiabilities}</h2>
          <span className="font-serif text-4xl sm:text-5xl font-bold tracking-tight text-[#B5836F]">
            {formatCurrency(totalLiabilitiesBase, settings.baseCurrency)}
          </span>
        </div>
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-[#B5836F]/5 blur-[100px] rounded-full" />
      </section>

      {/* LIST */}
      <section className="bg-white border border-[#E8E2D9] rounded-2xl shadow-sm overflow-hidden">
        <div className="p-6 border-b border-[#E8E2D9] flex justify-between items-center flex-wrap gap-4 select-none">
          <div>
            <h3 className="font-serif text-lg font-bold text-[#2D2926] flex items-center gap-2">
              <Landmark className="w-4 h-4 text-[#8C9A86]" />{t.liabilities}
            </h3>
            <p className="text-xs text-[#6B645E] font-semibold">{t.liabilitiesDesc}</p>
          </div>
          <button onClick={openAdd}
            className="flex items-center gap-1.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white px-5 py-2.5 rounded-full text-[11px] font-bold uppercase tracking-widest transition-all shadow-sm">
            <Plus className="w-3.5 h-3.5" />{t.addLiability}
          </button>
        </div>

        {/* Masaüstü: tam tablo. Mobilde bunun yerine aşağıdaki accordion listesi gösterilir. */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full text-left border-collapse select-none">
            <thead>
              <tr className="bg-[#F1EFE9] border-b border-[#E8E2D9] text-[10px] font-bold uppercase tracking-wider text-[#6B645E]">
                <th className="px-6 py-4">{t.liabilityName}</th>
                <th className="px-6 py-4">{t.liabilityType}</th>
                <th className="px-6 py-4 text-right">{t.liabilityAmount}</th>
                <th className="px-6 py-4 text-right">{t.liabilityInterestRate}</th>
                <th className="px-6 py-4 text-right">{t.liabilityDueDate}</th>
                <th className="px-6 py-4 text-center">{t.action}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E2D9]/40">
              {liabilities.length > 0 ? liabilities.map(l => (
                <tr key={l.id} className="hover:bg-[#F1EFE9]/30 transition-colors">
                  <td className="px-6 py-4">
                    <div className="text-sm font-semibold text-[#2D2926]">{l.name}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-[#E8E2D9] text-[#6B645E]">
                      {typeLabel(l.liability_type)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-[#B5836F] font-bold">
                    {formatCurrency(l.amount, l.currency)}
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-[#2D2926]">
                    {l.interest_rate != null ? `${l.interest_rate}%` : '—'}
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-[#2D2926]">
                    {l.due_date || '—'}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <button onClick={() => openEdit(l)} title={t.editLiability}
                        className="text-[#9E958C]/60 hover:text-[#8C9A86] p-1.5 rounded hover:bg-[#8C9A86]/10 transition-all">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setPendingDeleteId(l.id)} title={t.deleteLiability}
                        className="text-[#9E958C]/60 hover:text-[#B5836F] p-1.5 rounded hover:bg-[#B5836F]/10 transition-all">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={6} className="text-center py-12 text-sm text-[#6B645E]/70 font-semibold">{t.noLiabilities}</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobil: açılır/kapanır kart listesi */}
        <div className="md:hidden divide-y divide-[#E8E2D9]/60">
          {liabilities.length > 0 ? liabilities.map(l => {
            const isOpen = expandedMobileRow === l.id;
            return (
              <div key={l.id}>
                <button
                  type="button"
                  onClick={() => setExpandedMobileRow(v => (v === l.id ? null : l.id))}
                  className="w-full flex items-center gap-3 px-4 py-3.5 text-left"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-[#2D2926] truncate">{l.name}</div>
                    <span className="inline-block mt-0.5 text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-[#E8E2D9] text-[#6B645E]">
                      {typeLabel(l.liability_type)}
                    </span>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-mono font-bold text-[#B5836F]">{formatCurrency(l.amount, l.currency)}</div>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-[#9E958C] shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>

                {isOpen && (
                  <div className="px-4 pb-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3 bg-[#F1EFE9] border border-[#E8E2D9] rounded-xl p-3">
                      <div>
                        <div className="text-[9px] font-bold uppercase tracking-wider text-[#9E958C]">{t.liabilityInterestRate}</div>
                        <div className="text-xs font-mono font-bold text-[#2D2926] mt-0.5">{l.interest_rate != null ? `${l.interest_rate}%` : '—'}</div>
                      </div>
                      <div>
                        <div className="text-[9px] font-bold uppercase tracking-wider text-[#9E958C]">{t.liabilityDueDate}</div>
                        <div className="text-xs font-mono font-bold text-[#2D2926] mt-0.5">{l.due_date || '—'}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => openEdit(l)}
                        className="flex-1 py-2 rounded-lg bg-white border border-[#E8E2D9] text-[11px] font-bold uppercase tracking-wider text-[#6B645E] hover:text-[#2D2926] hover:bg-[#F1EFE9] transition-all flex items-center justify-center gap-1.5">
                        <Pencil className="w-3.5 h-3.5" />{t.editLiability}
                      </button>
                      <button onClick={() => setPendingDeleteId(l.id)} title={t.deleteLiability}
                        className="p-2.5 rounded-lg bg-white border border-[#E8E2D9] text-[#9E958C] hover:text-[#B5836F] hover:bg-[#B5836F]/10 transition-all">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          }) : (
            <div className="text-center py-12 text-sm text-[#6B645E]/70 font-semibold">{t.noLiabilities}</div>
          )}
        </div>
      </section>

      {/* ADD/EDIT MODAL */}
      <AnimatePresence>
        {showModal && (
          <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
              <div className="px-6 py-4 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F1EFE9]">
                <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
                  <Landmark className="w-4 h-4 text-[#8C9A86]" />
                  {editingId != null ? t.editLiability : t.addLiability}
                </h3>
                <button onClick={() => setShowModal(false)} aria-label={t.detailClose} className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors"><X className="w-4 h-4" /></button>
              </div>
              <form onSubmit={handleSubmit} className="p-6 space-y-4">
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityName}</label>
                  <input type="text" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-medium" />
                </div>

                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityType}</label>
                  <select value={form.liability_type} onChange={e => setForm({ ...form, liability_type: e.target.value as LiabilityType })}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold">
                    {LIABILITY_TYPES.map(type => (
                      <option key={type} value={type}>{typeLabel(type)}</option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityAmount}</label>
                    <input type="number" step="any" required min="0.01" value={form.amount || ''}
                      onChange={e => setForm({ ...form, amount: Number(e.target.value) })}
                      className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityCurrency}</label>
                    <select value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value as Liability['currency'] })}
                      className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold">
                      <option value="TRY">TRY</option>
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                      <option value="GBP">GBP</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityInterestRateOptional}</label>
                  <input type="number" step="any" min="0" value={form.interest_rate ?? ''}
                    onChange={e => setForm({ ...form, interest_rate: e.target.value === '' ? null : Number(e.target.value) })}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                </div>

                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.liabilityDueDateOptional}</label>
                  <input type="date" value={form.due_date ?? ''}
                    onChange={e => setForm({ ...form, due_date: e.target.value === '' ? null : e.target.value })}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <button type="button" onClick={() => setShowModal(false)}
                    className="px-5 py-2.5 rounded-full text-[11px] font-bold uppercase tracking-widest text-[#6B645E] hover:text-[#2D2926] hover:bg-[#E8E2D9] transition-all">
                    {t.cancelLiability}
                  </button>
                  <button type="submit" disabled={saving}
                    className="flex items-center gap-1.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white px-5 py-2.5 rounded-full text-[11px] font-bold uppercase tracking-widest transition-all shadow-sm disabled:opacity-60">
                    {t.saveLiability}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t.confirmDeleteTitle}
        message={t.confirmDeleteLiabilityBody}
        confirmLabel={t.deleteLiability}
        cancelLabel={t.cancelLiability}
        onConfirm={() => { if (pendingDeleteId !== null) onDeleteLiability(pendingDeleteId); setPendingDeleteId(null); }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
