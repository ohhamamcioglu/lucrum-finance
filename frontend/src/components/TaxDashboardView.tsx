import { useEffect, useState } from 'react';
import { AlertTriangle, Landmark, Calculator, PiggyBank, ExternalLink, CalendarClock, Coins } from 'lucide-react';
import { UserSettings } from '../types';
import { useT } from '../i18n';
import { api } from '../services/api';
import { formatCurrency } from '../utils';

interface TaxDashboardViewProps {
  settings: UserSettings;
}

type GermanySummary = Awaited<ReturnType<typeof api.getGermanyTaxSummary>>;
type UkSummary = Awaited<ReturnType<typeof api.getUkTaxSummary>>;
type VorabResult = Awaited<ReturnType<typeof api.calculateVorabpauschale>>;
type DividendEvent = Awaited<ReturnType<typeof api.getDividendCalendar>>['events'][number];

export default function TaxDashboardView({ settings }: TaxDashboardViewProps) {
  const t = useT(settings.language);

  // Almanya
  const [married, setMarried] = useState(false);
  const [germany, setGermany] = useState<GermanySummary | null>(null);
  const [germanyLoading, setGermanyLoading] = useState(true);

  const [basiszins, setBasiszins] = useState('');
  const [fundValueStart, setFundValueStart] = useState('');
  const [fundValueEnd, setFundValueEnd] = useState('');
  const [fundType, setFundType] = useState<'equity' | 'mixed' | 'other'>('equity');
  const [monthsHeld, setMonthsHeld] = useState(12);
  const [vorabResult, setVorabResult] = useState<VorabResult | null>(null);
  const [vorabLoading, setVorabLoading] = useState(false);

  // UK
  const [cgtAllowance, setCgtAllowance] = useState('');
  const [uk, setUk] = useState<UkSummary | null>(null);
  const [ukLoading, setUkLoading] = useState(true);

  // Temettü takvimi
  const [dividends, setDividends] = useState<DividendEvent[]>([]);
  const [dividendsLoading, setDividendsLoading] = useState(true);

  useEffect(() => {
    setGermanyLoading(true);
    api.getGermanyTaxSummary(married)
      .then(setGermany)
      .catch((err) => console.error('Germany tax summary fetch failed:', err))
      .finally(() => setGermanyLoading(false));
  }, [married]);

  useEffect(() => {
    setUkLoading(true);
    const allowance = cgtAllowance ? Number(cgtAllowance) : null;
    api.getUkTaxSummary(allowance)
      .then(setUk)
      .catch((err) => console.error('UK tax summary fetch failed:', err))
      .finally(() => setUkLoading(false));
  }, [cgtAllowance]);

  useEffect(() => {
    api.getDividendCalendar()
      .then((r) => setDividends(r.events))
      .catch((err) => console.error('Dividend calendar fetch failed:', err))
      .finally(() => setDividendsLoading(false));
  }, []);

  const handleCalculateVorab = async () => {
    if (!basiszins || !fundValueStart) return;
    setVorabLoading(true);
    try {
      const res = await api.calculateVorabpauschale({
        value_start_eur: Number(fundValueStart),
        basiszins_pct: Number(basiszins),
        fund_type: fundType,
        months_held: monthsHeld,
        value_end_eur: fundValueEnd ? Number(fundValueEnd) : null,
      });
      setVorabResult(res);
    } catch (err) {
      console.error('Vorabpauschale calculation failed:', err);
    } finally {
      setVorabLoading(false);
    }
  };

  const inputCls = "w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium";
  const labelCls = "block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif";
  const cardCls = "bg-white border border-[#E8E2D9] rounded-2xl p-5";
  const statBoxCls = "bg-[#F9F7F2] rounded-lg p-3";
  const statLabelCls = "text-[10px] uppercase text-[#9E958C] font-bold tracking-wider";
  const statValueCls = "text-sm font-mono font-bold text-[#2D2926] mt-1";

  return (
    <div className="space-y-6 pb-8">
      <div>
        <h2 className="text-xl font-serif font-bold text-[#2D2926]">{t.taxDashboardTitle}</h2>
        <p className="text-sm text-[#6B645E] mt-1">{t.taxDashboardSubtitle}</p>
      </div>

      <div className="flex items-start gap-3 bg-[#C9A876]/10 border border-[#C9A876]/30 rounded-xl px-4 py-3.5">
        <AlertTriangle className="w-4 h-4 text-[#C9A876] shrink-0 mt-0.5" />
        <p className="text-[12px] text-[#6B645E] leading-relaxed font-medium">{t.taxLegalDisclaimer}</p>
      </div>

      {/* ── ALMANYA ─────────────────────────────────────────────── */}
      <section className={cardCls}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
            <Landmark className="w-4 h-4 text-[#8C9A86]" />{t.taxGermanySection}
          </h3>
          <label className="flex items-center gap-2 text-[11px] font-medium text-[#6B645E] cursor-pointer">
            <input type="checkbox" checked={married} onChange={(e) => setMarried(e.target.checked)} className="accent-[#8C9A86]" />
            {t.taxMarried}
          </label>
        </div>

        <div className="space-y-5">
          {/* Sparerpauschbetrag */}
          <div>
            <h4 className="text-xs font-bold text-[#2D2926] flex items-center gap-1.5"><PiggyBank className="w-3.5 h-3.5 text-[#8C9A86]" />{t.taxSparerpauschbetrag}</h4>
            <p className="text-[11px] text-[#9E958C] mb-3">{t.taxSparerpauschbetragDesc}</p>
            {germanyLoading ? (
              <div className="h-16 bg-[#F1EFE9] rounded-lg animate-pulse" />
            ) : germany && (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <div className={statBoxCls}>
                    <div className={statLabelCls}>{t.taxRealizedGain}</div>
                    <div className={statValueCls}>{formatCurrency(germany.sparerpauschbetrag.realized_gain_eur, 'EUR')}</div>
                  </div>
                  <div className={statBoxCls}>
                    <div className={statLabelCls}>{t.taxExemption}</div>
                    <div className={statValueCls}>{formatCurrency(germany.sparerpauschbetrag.exemption_eur, 'EUR')}</div>
                  </div>
                  <div className={statBoxCls}>
                    <div className={statLabelCls}>{t.taxRemaining}</div>
                    <div className={`${statValueCls} text-[#8C9A86]`}>{formatCurrency(germany.sparerpauschbetrag.remaining_eur, 'EUR')}</div>
                  </div>
                </div>
                <div className="mt-3 h-1.5 bg-[#E8E2D9] rounded-full overflow-hidden">
                  <div className="h-full bg-[#8C9A86] transition-all" style={{ width: `${Math.min(100, germany.sparerpauschbetrag.used_pct)}%` }} />
                </div>
                {germany.sparerpauschbetrag.unconverted_events > 0 && (
                  <p className="text-[10px] text-[#B5836F] mt-2">{t.taxUnconvertedWarning(germany.sparerpauschbetrag.unconverted_events)}</p>
                )}
              </>
            )}
          </div>

          {/* Kripto lotlar */}
          <div className="border-t border-[#E8E2D9] pt-4">
            <h4 className="text-xs font-bold text-[#2D2926] flex items-center gap-1.5"><Coins className="w-3.5 h-3.5 text-[#8C9A86]" />{t.taxCryptoLots}</h4>
            <p className="text-[11px] text-[#9E958C] mb-3">{t.taxCryptoLotsDesc}</p>
            {germanyLoading ? (
              <div className="h-10 bg-[#F1EFE9] rounded-lg animate-pulse" />
            ) : germany && germany.crypto_lots.length > 0 ? (
              <div className="space-y-1.5">
                {germany.crypto_lots.map((lot, i) => (
                  <div key={i} className="flex items-center justify-between bg-[#F9F7F2] rounded-lg px-3 py-2 text-[12px]">
                    <div className="flex items-center gap-2 font-mono">
                      <span className="font-bold text-[#2D2926]">{lot.ticker}</span>
                      <span className="text-[#9E958C]">{lot.quantity} · {lot.buy_date}</span>
                    </div>
                    {lot.tax_free ? (
                      <span className="text-[10px] font-bold uppercase text-[#8C9A86] bg-[#8C9A86]/10 px-2 py-0.5 rounded-full">{t.taxCryptoTaxFree}</span>
                    ) : (
                      <span className="text-[10px] font-bold uppercase text-[#B5836F] bg-[#B5836F]/10 px-2 py-0.5 rounded-full">{t.taxCryptoDaysLeft(lot.days_until_tax_free)}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-[#9E958C]">{t.taxNoCryptoLots}</p>
            )}
          </div>

          {/* Vorabpauschale */}
          <div className="border-t border-[#E8E2D9] pt-4">
            <h4 className="text-xs font-bold text-[#2D2926] flex items-center gap-1.5"><Calculator className="w-3.5 h-3.5 text-[#8C9A86]" />{t.taxVorabpauschale}</h4>
            <p className="text-[11px] text-[#9E958C] mb-3">{t.taxVorabpauschaleDesc}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>{t.taxBasiszinsLabel}</label>
                <input type="number" step="0.01" value={basiszins} onChange={(e) => setBasiszins(e.target.value)} className={inputCls} placeholder="0.00" />
                <p className="text-[10px] text-[#9E958C] mt-1.5 leading-relaxed">
                  {t.taxBasiszinsHint}{' '}
                  <a href="https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuerarten/Investmentsteuer/investmentsteuer.html" target="_blank" rel="noopener noreferrer"
                    className="text-[#8C9A86] underline inline-flex items-center gap-0.5">
                    BMF <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                </p>
              </div>
              <div>
                <label className={labelCls}>{t.taxFundType}</label>
                <select value={fundType} onChange={(e) => setFundType(e.target.value as 'equity' | 'mixed' | 'other')}
                  className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold">
                  <option value="equity">{t.taxFundTypeEquity}</option>
                  <option value="mixed">{t.taxFundTypeMixed}</option>
                  <option value="other">{t.taxFundTypeOther}</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>{t.taxFundValueStart}</label>
                <input type="number" value={fundValueStart} onChange={(e) => setFundValueStart(e.target.value)} className={inputCls} placeholder="0.00" />
              </div>
              <div>
                <label className={labelCls}>{t.taxFundValueEnd}</label>
                <input type="number" value={fundValueEnd} onChange={(e) => setFundValueEnd(e.target.value)} className={inputCls} placeholder="0.00" />
                <p className="text-[10px] text-[#9E958C] mt-1.5">{t.taxFundValueEndHint}</p>
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>{t.taxMonthsHeld}: {monthsHeld}</label>
                <input type="range" min={1} max={12} value={monthsHeld} onChange={(e) => setMonthsHeld(Number(e.target.value))} className="w-full accent-[#8C9A86]" />
              </div>
            </div>
            <button onClick={handleCalculateVorab} disabled={!basiszins || !fundValueStart || vorabLoading}
              className="mt-4 px-6 py-2.5 bg-[#8C9A86] hover:bg-[#7A8874] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">
              {t.taxCalculate}
            </button>
            {vorabResult && (
              <div className="mt-4 bg-[#F9F7F2] rounded-lg p-4">
                <div className={statLabelCls}>{t.taxTaxableBase}</div>
                <div className="text-lg font-mono font-bold text-[#2D2926] mt-1">{formatCurrency(vorabResult.taxable_base_eur, 'EUR')}</div>
                <div className="text-[10px] text-[#9E958C] mt-1">{vorabResult.teilfreistellung_pct}% Teilfreistellung</div>
                {vorabResult.capped_by_actual_gain && <p className="text-[10px] text-[#8C9A86] mt-1.5 font-medium">{t.taxCappedNotice}</p>}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── UK ──────────────────────────────────────────────────── */}
      <section className={cardCls}>
        <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif mb-4">
          <Landmark className="w-4 h-4 text-[#8C9A86]" />{t.taxUkSection}
        </h3>

        <div className="space-y-5">
          {/* ISA limit */}
          <div>
            <h4 className="text-xs font-bold text-[#2D2926]">{t.taxIsaAllowance}</h4>
            <p className="text-[11px] text-[#9E958C] mb-3">{t.taxIsaAllowanceDesc}</p>
            {ukLoading ? (
              <div className="h-16 bg-[#F1EFE9] rounded-lg animate-pulse" />
            ) : uk && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className={statBoxCls}>
                    <div className={statLabelCls}>{t.taxIsaUsed}</div>
                    <div className={statValueCls}>{formatCurrency(uk.isa_allowance.used_gbp, 'GBP')}</div>
                  </div>
                  <div className={statBoxCls}>
                    <div className={statLabelCls}>{t.taxIsaRemaining}</div>
                    <div className={`${statValueCls} text-[#8C9A86]`}>{formatCurrency(uk.isa_allowance.remaining_gbp, 'GBP')}</div>
                  </div>
                </div>
                <div className="mt-3 h-1.5 bg-[#E8E2D9] rounded-full overflow-hidden">
                  <div className="h-full bg-[#8C9A86] transition-all" style={{ width: `${Math.min(100, uk.isa_allowance.used_pct)}%` }} />
                </div>
              </>
            )}
          </div>

          {/* Bed-and-ISA */}
          <div className="border-t border-[#E8E2D9] pt-4">
            <h4 className="text-xs font-bold text-[#2D2926]">{t.taxBedAndIsa}</h4>
            <p className="text-[11px] text-[#9E958C] mb-3">{t.taxBedAndIsaDesc}</p>
            <div className="max-w-xs">
              <label className={labelCls}>{t.taxCgtAllowanceLabel}</label>
              <input type="number" value={cgtAllowance} onChange={(e) => setCgtAllowance(e.target.value)} className={inputCls} placeholder="3000" />
              <p className="text-[10px] text-[#9E958C] mt-1.5">
                {t.taxCgtAllowanceHint}{' '}
                <a href="https://www.gov.uk/capital-gains-tax/allowances" target="_blank" rel="noopener noreferrer"
                  className="text-[#8C9A86] underline inline-flex items-center gap-0.5">
                  {t.taxCgtAllowanceCheck} <ExternalLink className="w-2.5 h-2.5" />
                </a>
              </p>
            </div>
            {uk?.bed_and_isa && (
              <div className="mt-3 bg-[#F9F7F2] rounded-lg p-4 space-y-1.5">
                <div className="flex justify-between text-[12px]">
                  <span className="text-[#6B645E]">{t.taxGiaGain}</span>
                  <span className="font-mono font-bold text-[#2D2926]">{formatCurrency(uk.bed_and_isa.total_gia_unrealized_gain_gbp, 'GBP')}</span>
                </div>
                {uk.bed_and_isa.exceeds_allowance ? (
                  <p className="text-[11px] font-medium text-[#B5836F]">{t.taxExceedsAllowance} {formatCurrency(uk.bed_and_isa.excess_gbp, 'GBP')}</p>
                ) : (
                  <p className="text-[11px] font-medium text-[#8C9A86]">{t.taxWithinAllowance}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── TEMETTÜ TAKVİMİ ─────────────────────────────────────── */}
      <section className={cardCls}>
        <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif mb-1">
          <CalendarClock className="w-4 h-4 text-[#8C9A86]" />{t.taxDividendCalendarSection}
        </h3>
        <p className="text-[11px] text-[#9E958C] mb-4">{t.dividendCalendarDesc}</p>
        {dividendsLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-12 bg-[#F1EFE9] rounded-lg animate-pulse" />)}
          </div>
        ) : dividends.length === 0 ? (
          <p className="text-[12px] text-[#9E958C]">{t.dividendCalendarEmpty}</p>
        ) : (
          <div className="space-y-1.5">
            {dividends.map((d, i) => (
              <div key={i} className="flex items-center justify-between bg-[#F9F7F2] rounded-lg px-3 py-2.5">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-[#2D2926]">{d.ticker}</span>
                    <span className="text-[11px] text-[#9E958C] font-mono">{d.ex_date}</span>
                    {d.is_future && (
                      <span className="text-[9px] font-bold uppercase text-[#8C9A86] bg-[#8C9A86]/10 px-1.5 py-0.5 rounded-full">{t.dividendUpcoming}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-[#9E958C] mt-0.5">
                    {formatCurrency(d.amount_per_share, 'USD')} {t.dividendPerShare} × {d.quantity_held}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[9px] uppercase text-[#9E958C] font-bold">{t.dividendYourTotal}</div>
                  <div className="text-sm font-mono font-bold text-[#8C9A86]">{formatCurrency(d.total_amount, 'USD')}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
