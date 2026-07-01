import { useState, useEffect, useRef, useMemo } from 'react';
import { motion } from 'motion/react';
import { Landmark, AlertTriangle, CheckCircle, Info, Loader2, ShieldCheck, ShieldAlert, Shield } from 'lucide-react';
import { Holding, UserSettings } from '../types';
import { STRESS_SCENARIOS, runStressTest, computeCorrelationMatrix, formatCurrency, CorrMatrix } from '../utils';
import { useT } from '../i18n';
import { api } from '../services/api';

interface RiskViewProps {
  holdings: Array<Holding & { value: number; cost: number; unrealizedPL: number; unrealizedPLPercent: number; allocationPercent: number }>;
  settings: UserSettings;
}

// Kategori → backend asset class eşlemesi (getPriceHistory için)
function toApiAssetClass(h: { category: string; assetClass?: string }): string {
  if (h.assetClass) return h.assetClass;
  if (h.category === 'Crypto') return 'Kripto';
  if (h.category === 'FixedIncome') return 'FixedIncome';
  if (h.category === 'Cash') return 'Nakit';
  return 'ABD Hisse/ETF';
}

export default function RiskView({ holdings, settings }: RiskViewProps) {
  const t = useT(settings.language);
  const [selectedScenarioIndex, setSelectedScenarioIndex] = useState(0);
  const [corrData, setCorrData] = useState<CorrMatrix | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);
  const prevSymsRef = useRef('');

  const activeScenario = STRESS_SCENARIOS[selectedScenarioIndex];

  const holdingsForStress = holdings.map(h => ({
    id: h.id, symbol: h.symbol, name: h.name, category: h.category,
    sector: h.sector, shares: h.shares, avgBuyPrice: h.avgBuyPrice,
    currentPrice: h.currentPrice, riskScore: h.riskScore
  }));

  const stressResult = runStressTest(holdingsForStress, activeScenario);

  // Bar genişliği: her holding'in toplam kayıptaki payı (oransal)
  const maxAbsDiff = useMemo(
    () => Math.max(...stressResult.results.map(r => Math.abs(r.difference)), 1),
    [stressResult]
  );

  const nonCashHoldings = useMemo(
    () => holdings.filter(h => h.category !== 'Cash'),
    [holdings]
  );
  const nonCashSymKey = useMemo(
    () => nonCashHoldings.map(h => h.symbol).sort().join(','),
    [nonCashHoldings]
  );

  useEffect(() => {
    if (nonCashHoldings.length < 2) { setCorrData(null); return; }
    if (nonCashSymKey === prevSymsRef.current) return;
    prevSymsRef.current = nonCashSymKey;

    let cancelled = false;
    setCorrLoading(true);

    Promise.all(
      nonCashHoldings.map(h =>
        // FIX: h.assetClass kullan (BIST, Kripto vs. doğru routing için)
        api.getPriceHistory(h.symbol, 180, toApiAssetClass(h))
          .then(data => ({ symbol: h.symbol, data }))
          .catch(() => ({ symbol: h.symbol, data: [] as { date: string; price: number }[] }))
      )
    ).then(results => {
      if (cancelled) return;
      const histories: Record<string, { date: string; price: number }[]> = {};
      for (const r of results) if (r.data.length > 2) histories[r.symbol] = r.data;
      setCorrData(computeCorrelationMatrix(histories));
      setCorrLoading(false);
    });

    return () => { cancelled = true; };
  }, [nonCashSymKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Portföy risk profili: equity ağırlığı + ortalama beta
  const portfolioRiskProfile = useMemo(() => {
    const totalValue = holdings.reduce((s, h) => s + h.value, 0);
    if (totalValue === 0) return null;
    const equityW = holdings.filter(h => h.category === 'Equity').reduce((s, h) => s + h.value, 0) / totalValue;
    const cryptoW = holdings.filter(h => h.category === 'Crypto').reduce((s, h) => s + h.value, 0) / totalValue;
    const avgBeta = holdings
      .filter(h => h.category !== 'Cash')
      .reduce((s, h) => s + (h.riskScore / 4) * (h.value / totalValue), 0);
    const score = equityW * 0.4 + cryptoW * 0.5 + Math.min(avgBeta / 3, 0.5) * 0.1;
    return { equityW, cryptoW, avgBeta, score };
  }, [holdings]);

  const getPortfolioRating = () => {
    if (!portfolioRiskProfile) return null;
    const { score, avgBeta } = portfolioRiskProfile;
    if (score > 0.55 || avgBeta > 1.8) return {
      label: 'Yüksek Risk', color: 'text-[#B5836F]', bg: 'bg-[#B5836F]/10 border-[#B5836F]/30',
      Icon: ShieldAlert,
      desc: `Ortalama beta ${avgBeta.toFixed(2)} — portföy piyasa hareketlerine karşı hassas. Dalgalanmalarda kayıp büyüyebilir.`
    };
    if (score > 0.3 || avgBeta > 1.1) return {
      label: 'Dengeli', color: 'text-[#8C9A86]', bg: 'bg-[#8C9A86]/10 border-[#8C9A86]/30',
      Icon: Shield,
      desc: `Ortalama beta ${avgBeta.toFixed(2)} — makul risk seviyesi. Hem büyüme hem koruma dengesi kurulmuş.`
    };
    return {
      label: 'Savunmacı', color: 'text-[#7A8874]', bg: 'bg-[#7A8874]/10 border-[#7A8874]/30',
      Icon: ShieldCheck,
      desc: `Ortalama beta ${avgBeta.toFixed(2)} — düşük volatilite. Kriz dönemlerinde görece dirençli.`
    };
  };

  const getStressAdvice = (pct: number) => {
    if (pct < -20) return { label: t.highRiskRating, style: 'text-[#B5836F]', Icon: AlertTriangle };
    if (pct < -5)  return { label: t.balancedRating, style: 'text-[#8C9A86]',  Icon: Info };
    return          { label: t.resilientRating,  style: 'text-[#7A8874]',  Icon: CheckCircle };
  };

  const stressAdvice = getStressAdvice(stressResult.totalPctChange);
  const portfolioRating = getPortfolioRating();

  const getCorrBgColor = (val: number) => {
    if (val === 1.0)  return 'bg-[#8C9A86]/25 text-[#8C9A86]';
    if (val > 0.6)    return 'bg-[#B5836F]/25 text-[#B5836F]';
    if (val > 0.3)    return 'bg-[#B5836F]/15 text-[#B5836F]/80';
    if (val < 0)      return 'bg-[#7A9FBF]/20 text-[#5A7F9F]';
    return 'bg-[#F1EFE9] text-[#9E958C]';
  };

  return (
    <div className="space-y-6 select-none">

      <div>
        <h2 className="text-xl font-bold text-[#2D2926]">{t.riskTitle}</h2>
        <p className="text-xs text-[#6B645E] mt-0.5">{t.riskSubtitle}</p>
      </div>

      {/* Portföy risk profili — senaryo bağımsız genel değerlendirme */}
      {portfolioRating && holdings.length > 0 && (
        <div className={`flex items-start gap-4 p-4 rounded-xl border ${portfolioRating.bg}`}>
          <portfolioRating.Icon className={`w-5 h-5 shrink-0 mt-0.5 ${portfolioRating.color}`} />
          <div className="flex-1">
            <div className={`text-xs font-bold uppercase tracking-wider ${portfolioRating.color}`}>
              Portföy Risk Profili: {portfolioRating.label}
            </div>
            <p className="text-[11px] text-[#6B645E] mt-1 leading-relaxed">{portfolioRating.desc}</p>
          </div>
          <div className="text-right shrink-0">
            <div className={`text-xs font-bold ${portfolioRating.color}`}>β {portfolioRiskProfile!.avgBeta.toFixed(2)}</div>
            <div className="text-[10px] text-[#9E958C]">ort. beta</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* LEFT: SCENARIO SELECTOR */}
        <div className="space-y-4 lg:col-span-1">
          <div id="risk-scenarios-selector" className="bg-white border border-[#E8E2D9] p-5 rounded-2xl shadow-sm">
            <h3 className="font-sans text-xs font-bold text-[#2D2926] uppercase tracking-wider mb-4">
              {t.selectScenario}
            </h3>
            <div className="space-y-2">
              {STRESS_SCENARIOS.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setSelectedScenarioIndex(index)}
                  className={`w-full text-left p-3.5 rounded-lg border transition-all ${
                    selectedScenarioIndex === index
                      ? 'bg-[#B5836F]/10 border-[#B5836F] text-[#B5836F]'
                      : 'bg-[#F1EFE9] border-[#E8E2D9] text-[#6B645E] hover:bg-[#E8E2D9] hover:text-[#2D2926]'
                  }`}
                >
                  <div className="text-xs font-bold">{t.scenarioNames[index]}</div>
                  <div className="text-[10px] text-[#9E958C] mt-1 truncate">{t.scenarioDescs[index]}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Senaryo sonucu özet */}
          {holdings.length > 0 && (
            <div className="bg-white border border-[#E8E2D9] p-4 rounded-xl">
              <div className="flex items-center gap-2 mb-1">
                <stressAdvice.Icon className={`w-4 h-4 ${stressAdvice.style}`} />
                <span className={`text-xs font-bold uppercase tracking-wider ${stressAdvice.style}`}>
                  {stressAdvice.label}
                </span>
              </div>
              <p className="text-[10px] text-[#9E958C] leading-relaxed">
                Bu senaryo gerçekleşseydi portföy{' '}
                <span className={stressResult.totalPctChange < 0 ? 'font-bold text-[#B5836F]' : 'font-bold text-[#7A8874]'}>
                  {stressResult.totalPctChange >= 0 ? '+' : ''}{stressResult.totalPctChange.toFixed(1)}%
                </span>{' '}
                değişirdi.
              </p>
            </div>
          )}
        </div>

        {/* RIGHT: STRESS OUTCOMES */}
        <div id="risk-stress-outcomes" className="lg:col-span-2 bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="font-sans text-sm font-bold text-[#2D2926]">{t.scenarioImpact}</h3>
              <p className="text-[11px] text-[#6B645E]">Beta'ya göre düzeltilmiş etki · {activeScenario.name}</p>
            </div>
            <div className="text-right">
              <span className="text-[10px] uppercase font-bold text-[#9E958C] tracking-wider">{t.stressEstimate}</span>
              <div className={`text-lg font-bold font-mono mt-0.5 ${stressResult.totalDifference >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                {stressResult.totalDifference >= 0 ? '+' : ''}{stressResult.totalPctChange.toFixed(2)}%
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 bg-[#F1EFE9] p-3 border border-[#E8E2D9] rounded-lg mb-4">
            <div>
              <span className="text-[10px] text-[#9E958C] block font-medium">{t.initialCapital}</span>
              <span className="text-sm font-mono font-bold text-[#2D2926]">
                {formatCurrency(stressResult.initialTotal, settings.baseCurrency)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-[#9E958C] block font-medium">{t.stressedValue}</span>
              <span className="text-sm font-mono font-bold text-[#2D2926]">
                {formatCurrency(stressResult.stressTotal, settings.baseCurrency)}
              </span>
            </div>
          </div>

          <div className="space-y-3 flex-1 overflow-y-auto custom-scrollbar max-h-72 pr-1">
            {holdings.length > 0 ? (
              stressResult.results
                .slice()
                .sort((a, b) => a.difference - b.difference) // en çok kayıp en üstte
                .map(res => {
                  const isLoss = res.difference < 0;
                  // Bar genişliği: bu holding'in mutlak $ etkisi / en büyük $ etkisi
                  const barWidth = Math.round(Math.min(100, (Math.abs(res.difference) / maxAbsDiff) * 100));
                  return (
                    <div key={res.symbol} className="space-y-1.5">
                      <div className="flex justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-[#2D2926]">{res.symbol}</span>
                          <span className="text-[10px] text-[#9E958C] uppercase tracking-wider">{res.category}</span>
                          {res.category === 'Equity' && (
                            <span className="text-[9px] text-[#B5AFA8]">
                              β{((holdingsForStress.find(h => h.symbol === res.symbol)?.riskScore ?? 4) / 4).toFixed(1)}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 font-mono text-right">
                          <span className="text-[#9E958C] text-[10px]">
                            {formatCurrency(res.stressedValue, settings.baseCurrency)}
                          </span>
                          <span className={`font-bold min-w-[40px] text-right ${isLoss ? 'text-[#B5836F]' : 'text-[#7A8874]'}`}>
                            {res.pctChange >= 0 ? '+' : ''}{res.pctChange.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                      <div className="w-full bg-[#F1EFE9] h-2 rounded-full overflow-hidden">
                        <motion.div
                          className={`h-full rounded-full ${isLoss ? 'bg-[#B5836F]' : 'bg-[#7A8874]'}`}
                          initial={{ width: 0 }}
                          animate={{ width: `${barWidth}%` }}
                          transition={{ duration: 0.4, ease: 'easeOut' }}
                        />
                      </div>
                    </div>
                  );
                })
            ) : (
              <div className="py-12 text-center text-sm text-[#9E958C] font-medium">
                {t.addAssetsForRisk}
              </div>
            )}
          </div>

          <p className="text-[10px] text-[#B5AFA8] mt-3 pt-3 border-t border-[#F1EFE9]">
            Bar genişliği: her varlığın senaryodaki mutlak $ etkisine oransal. Hisse etkisi beta ile ölçeklendirilir.
          </p>
        </div>
      </div>

      {/* CORRELATION MATRIX */}
      {nonCashHoldings.length > 1 && (
        <section id="asset-correlation-matrix" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm">
          <div className="mb-6">
            <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-1">
              <Landmark className="w-4 h-4 text-[#8C9A86]" />
              {t.corrMatrix}
            </h3>
            <p className="text-[11px] text-[#6B645E]">{t.corrMatrixDesc}</p>
          </div>

          {corrLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-[#9E958C]">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs font-medium">180 günlük fiyat verisi hesaplanıyor…</span>
            </div>
          )}

          {!corrLoading && corrData && corrData.symbols.length > 1 && (
            <div className="overflow-x-auto">
              <div className="min-w-[500px] flex flex-col">
                <div className="flex border-b border-[#E8E2D9] pb-2">
                  <div className="w-24 shrink-0 font-bold text-xs text-[#9E958C]">VARLIK</div>
                  {corrData.symbols.map(sym => (
                    <div key={sym} className="flex-1 text-center font-mono font-bold text-xs text-[#6B645E] uppercase">
                      {sym.replace('.IS', '')}
                    </div>
                  ))}
                </div>

                <div className="divide-y divide-[#E8E2D9]/30 mt-2 space-y-1">
                  {corrData.matrix.map(row => (
                    <div key={row.symbol} className="flex items-center py-1">
                      <div className="w-24 shrink-0 font-bold text-xs text-[#2D2926] uppercase font-mono">
                        {row.symbol.replace('.IS', '')}
                      </div>
                      {row.correlations.map(cell => (
                        <div
                          key={cell.symbol}
                          className={`flex-1 text-center font-mono text-xs font-semibold py-2 mx-0.5 rounded border border-[#E8E2D9]/40 cursor-help transition-all ${getCorrBgColor(cell.value)}`}
                          title={`${row.symbol} — ${cell.symbol}: ${cell.value.toFixed(2)} (${cell.commonDays} ortak gün)`}
                        >
                          {cell.value === 1.0 ? '1.00' : cell.value.toFixed(2)}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>

                {/* Renk açıklaması */}
                <div className="flex items-center gap-4 mt-4 pt-3 border-t border-[#F1EFE9]">
                  <span className="text-[10px] text-[#9E958C] font-medium">Korelasyon:</span>
                  {[
                    { label: '> 0.6 Yüksek', cls: 'bg-[#B5836F]/25 text-[#B5836F]' },
                    { label: '0.3–0.6 Orta', cls: 'bg-[#B5836F]/15 text-[#B5836F]/80' },
                    { label: '0–0.3 Düşük', cls: 'bg-[#F1EFE9] text-[#9E958C]' },
                    { label: '< 0 Negatif', cls: 'bg-[#7A9FBF]/20 text-[#5A7F9F]' },
                  ].map(({ label, cls }) => (
                    <span key={label} className={`text-[9px] font-bold px-2 py-0.5 rounded ${cls}`}>{label}</span>
                  ))}
                </div>

                <p className="text-[10px] text-[#B5AFA8] mt-2">
                  Son 180 günlük günlük getirilerden Pearson korelasyonu.
                </p>
              </div>
            </div>
          )}

          {!corrLoading && (!corrData || corrData.symbols.length <= 1) && (
            <div className="py-8 text-center text-xs text-[#9E958C] font-medium">
              Korelasyon hesaplamak için en az 2 varlıkta yeterli fiyat geçmişi gerekli.
            </div>
          )}
        </section>
      )}

    </div>
  );
}
