import { useState } from 'react';
import { motion } from 'motion/react';
import { Percent, Activity, RefreshCw } from 'lucide-react';
import { Holding, UserSettings } from '../types';
import { formatCurrency } from '../utils';
import { useT } from '../i18n';

interface AnalyticsViewProps {
  holdings: Array<Holding & { value: number; cost: number; unrealizedPL: number; unrealizedPLPercent: number; allocationPercent: number }>;
  totalValue: number;
  settings: UserSettings;
}

export default function AnalyticsView({ holdings, totalValue, settings }: AnalyticsViewProps) {
  const t = useT(settings.language);

  const nonCashHoldings = holdings.filter(h => h.category !== 'Cash');
  const [selectedAssetSymbol, setSelectedAssetSymbol] = useState(nonCashHoldings[0]?.symbol || '');
  const [priceMultiplier, setPriceMultiplier] = useState(0);

  const activeAsset = holdings.find(h => h.symbol === selectedAssetSymbol);

  const sectorGroups = holdings.reduce((acc, h) => {
    if (!acc[h.sector]) acc[h.sector] = 0;
    acc[h.sector] += h.value;
    return acc;
  }, {} as Record<string, number>);

  const sectorAllocations = Object.entries(sectorGroups)
    .map(([sector, val]) => ({
      sector,
      value: val,
      percent: totalValue > 0 ? (val / totalValue) * 100 : 0
    }))
    .sort((a, b) => b.value - a.value);

  const getSimulationResult = () => {
    if (!activeAsset) return { newValue: totalValue, difference: 0, newPercent: 0 };
    const assetValue = activeAsset.value;
    const diff = assetValue * (priceMultiplier / 100);
    const simulatedTotalValue = totalValue + diff;
    const simulatedAssetValue = assetValue + diff;
    const simulatedAssetPercent = simulatedTotalValue > 0 ? (simulatedAssetValue / simulatedTotalValue) * 100 : 0;
    return { newValue: simulatedTotalValue, difference: diff, newPercent: simulatedAssetPercent };
  };

  const simResult = getSimulationResult();

  return (
    <div className="space-y-6">

      <div className="flex justify-between items-center select-none">
        <div>
          <h2 className="text-xl font-bold text-[#2D2926]">{t.analyticsTitle}</h2>
          <p className="text-xs text-[#6B645E] mt-0.5">{t.analyticsSubtitle}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* SECTOR EXPOSURE */}
        <div id="analytics-sector-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-1">
              <Percent className="w-4 h-4 text-[#8C9A86]" />
              {t.sectorExposure}
            </h3>
            <p className="text-[11px] text-[#6B645E] mb-6">{t.sectorExposureDesc}</p>
          </div>

          <div className="space-y-4 flex-1 flex flex-col justify-center">
            {sectorAllocations.map((sec, idx) => (
              <div key={sec.sector} className="space-y-1.5">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-semibold text-[#2D2926]">{sec.sector}</span>
                  <div className="space-x-3 text-right">
                    <span className="text-[#6B645E] font-mono">
                      {formatCurrency(sec.value, settings.baseCurrency)}
                    </span>
                    <span className="font-mono font-bold text-[#8C9A86]">
                      {sec.percent.toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="w-full bg-[#E8E2D9] h-2 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${sec.percent}%` }}
                    transition={{ duration: 0.8, delay: idx * 0.1 }}
                    className="h-full bg-gradient-to-r from-[#8C9A86]/40 to-[#8C9A86] rounded-full"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* POSITION YIELDS */}
        <div id="analytics-performance-spread-card" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col">
          <div>
            <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-1">
              <Activity className="w-4 h-4 text-[#7A8874]" />
              {t.positionYields}
            </h3>
            <p className="text-[11px] text-[#6B645E] mb-6">{t.positionYieldsDesc}</p>
          </div>

          <div className="space-y-3.5 flex-1 overflow-y-auto custom-scrollbar max-h-80 pr-1 select-none">
            {holdings.map((h) => {
              if (h.category === 'Cash') {
                return (
                  <div key={h.id} className="flex items-center justify-between gap-4 opacity-60">
                    <div className="w-24 shrink-0 text-left">
                      <div className="text-xs font-bold text-[#2D2926]">{h.symbol}</div>
                      <div className="text-[10px] text-[#6B645E] font-medium">Nakit</div>
                    </div>
                    <div className="flex-1 h-5 flex items-center relative bg-[#F1EFE9] rounded overflow-hidden px-2 border border-[#E8E2D9]/50">
                      <span className="absolute left-2 text-[10px] font-mono font-semibold text-[#9E958C]">—</span>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-xs font-mono font-bold text-[#9E958C]">
                        {formatCurrency(h.value, settings.baseCurrency)}
                      </span>
                    </div>
                  </div>
                );
              }
              const isProfit = h.unrealizedPL >= 0;
              const absPercent = Math.min(Math.abs(h.unrealizedPLPercent), 100);
              return (
                <div key={h.id} className="flex items-center justify-between gap-4">
                  <div className="w-24 shrink-0 text-left">
                    <div className="text-xs font-bold text-[#2D2926]">{h.symbol}</div>
                    <div className="text-[10px] text-[#6B645E] font-medium truncate">{h.name}</div>
                  </div>

                  <div className="flex-1 h-5 flex items-center relative bg-[#F1EFE9] rounded overflow-hidden px-2 border border-[#E8E2D9]/50">
                    <div
                      className={`h-full opacity-35 ${isProfit ? 'bg-[#7A8874]' : 'bg-[#B5836F]'}`}
                      style={{ width: `${absPercent}%` }}
                    />
                    <span className="absolute left-2 text-[10px] font-mono font-semibold text-[#2D2926]/90">
                      {isProfit ? '+' : ''}{h.unrealizedPLPercent.toFixed(1)}%
                    </span>
                  </div>

                  <div className="text-right shrink-0">
                    <span className={`text-xs font-mono font-bold ${isProfit ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                      {isProfit ? '+' : ''}
                      {formatCurrency(h.unrealizedPL, settings.baseCurrency)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* WHAT-IF SIMULATOR */}
      <section id="predictive-whatif-simulator" className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm select-none">
        <div>
          <h3 className="font-sans text-sm font-bold text-[#2D2926] flex items-center gap-2 mb-1">
            <RefreshCw className="w-4 h-4 text-[#B5836F]" />
            {t.simulator}
          </h3>
          <p className="text-[11px] text-[#6B645E] mb-6">{t.simulatorDesc}</p>
        </div>

        {nonCashHoldings.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

            {/* Asset Selector */}
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-[#6B645E] mb-1.5">
                  {t.selectAsset}
                </label>
                <div className="grid grid-cols-3 gap-1.5">
                  {nonCashHoldings.map((h) => (
                    <button
                      key={h.id}
                      id={`sim-select-btn-${h.symbol}`}
                      onClick={() => { setSelectedAssetSymbol(h.symbol); setPriceMultiplier(0); }}
                      className={`px-2 py-1.5 rounded text-xs font-mono font-bold border text-center transition-all ${
                        selectedAssetSymbol === h.symbol
                          ? 'bg-[#B5836F]/15 border-[#B5836F] text-[#B5836F]'
                          : 'bg-[#F1EFE9] border-[#E8E2D9] text-[#6B645E] hover:text-[#2D2926]'
                      }`}
                    >
                      {h.symbol}
                    </button>
                  ))}
                </div>
              </div>

              {activeAsset && (
                <div className="p-3 bg-[#F1EFE9] border border-[#E8E2D9] rounded text-xs">
                  <div className="text-[10px] font-bold uppercase text-[#9E958C] mb-1">{t.posSpecs}</div>
                  <div className="flex justify-between py-0.5">
                    <span className="text-[#6B645E]">{t.tickerShares}</span>
                    <span className="font-mono text-[#2D2926] font-semibold">{activeAsset.symbol} • {activeAsset.shares}</span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <span className="text-[#6B645E]">{t.marketPrice}</span>
                    <span className="font-mono text-[#2D2926] font-semibold">{formatCurrency(activeAsset.currentPrice, settings.baseCurrency)}</span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <span className="text-[#6B645E]">{t.totalExposure}</span>
                    <span className="font-mono text-[#2D2926] font-semibold">{formatCurrency(activeAsset.value, settings.baseCurrency)}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Slider */}
            <div className="flex flex-col justify-center space-y-4">
              <div>
                <div className="flex justify-between text-xs font-bold mb-2">
                  <span className="text-[#6B645E]">{t.simPriceAdj}</span>
                  <span className={`font-mono ${priceMultiplier >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                    {priceMultiplier >= 0 ? '+' : ''}{priceMultiplier}%
                  </span>
                </div>
                <input
                  id="sim-price-multiplier-slider"
                  type="range" min="-100" max="100" step="5"
                  value={priceMultiplier}
                  onChange={(e) => setPriceMultiplier(Number(e.target.value))}
                  className="w-full accent-[#8C9A86] h-1.5 bg-[#E8E2D9] rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[9px] text-[#9E958C] mt-1.5 font-bold uppercase tracking-wider">
                  <span>-100% ({t.totalLoss})</span>
                  <span>0% ({t.baseline})</span>
                  <span>+100% ({t.doubled})</span>
                </div>
              </div>

              {activeAsset && (
                <div className="text-xs text-[#6B645E] font-medium leading-relaxed">
                  {t.adjustingSlider(
                    activeAsset.symbol,
                    formatCurrency(activeAsset.currentPrice * (1 + priceMultiplier / 100), settings.baseCurrency)
                  )}
                </div>
              )}
            </div>

            {/* Outcome */}
            <div className="bg-[#F1EFE9] border border-[#E8E2D9] p-5 rounded-xl flex flex-col justify-center">
              <div className="text-[10px] font-bold uppercase text-[#9E958C] mb-3 tracking-widest">
                {t.simOutcome}
              </div>
              <div className="space-y-3.5">
                <div>
                  <span className="text-[11px] text-[#6B645E] block font-medium">{t.newSimValue}</span>
                  <span className="text-xl font-bold font-mono text-[#2D2926]">
                    {formatCurrency(simResult.newValue, settings.baseCurrency)}
                  </span>
                </div>
                <div className="h-[1px] bg-[#E8E2D9]" />
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-[10px] text-[#9E958C] block font-semibold">{t.netExposureDelta}</span>
                    <span className={`text-sm font-bold font-mono ${simResult.difference >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                      {simResult.difference >= 0 ? '+' : ''}
                      {formatCurrency(simResult.difference, settings.baseCurrency)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#9E958C] block font-semibold">{t.newConcentration}</span>
                    <span className="text-sm font-bold font-mono text-[#8C9A86]">
                      {simResult.newPercent.toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        ) : (
          <div className="py-12 text-center text-sm text-[#9E958C] font-medium">
            {t.addAssetsForSim}
          </div>
        )}
      </section>

    </div>
  );
}
