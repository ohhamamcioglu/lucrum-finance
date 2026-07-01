import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import DashboardView from './components/DashboardView';
import AnalyticsView from './components/AnalyticsView';
import RiskView from './components/RiskView';
import MarketsView from './components/MarketsView';
import SettingsView from './components/SettingsView';
import NewsView from './components/NewsView';

import { Holding, ActiveTab, UserSettings, AssetCategory } from './types';
import { INITIAL_SETTINGS, MARKET_ASSETS, calculatePortfolio, convertCurrency } from './utils';
import { api } from './services/api';
import { useT } from './i18n';
import { useAuth } from './AuthContext';

// Modül-level: sayfa değişse / component yeniden mount olsa bile risk skorları korunur
const _riskCache: Record<string, number> = {};

const BENCHMARK_TICKERS: Record<string, { ticker: string; assetClass: string }> = {
  'S&P 500':    { ticker: 'SPY',       assetClass: 'ABD Hisse/ETF' },
  'Nasdaq':     { ticker: 'QQQ',       assetClass: 'ABD Hisse/ETF' },
  'Bitcoin':    { ticker: 'BTC-USD',   assetClass: 'Kripto' },
  'Gold':       { ticker: 'GC=F',      assetClass: 'ABD Hisse/ETF' },
  'BIST100':    { ticker: 'XU100.IS',  assetClass: 'BIST Hissesi' },
  'DAX':        { ticker: '^GDAXI',    assetClass: 'ABD Hisse/ETF' },
  'FTSE 100':   { ticker: '^FTSE',     assetClass: 'ABD Hisse/ETF' },
  'CAC 40':     { ticker: '^FCHI',     assetClass: 'ABD Hisse/ETF' },
  'Euro Stoxx': { ticker: '^STOXX50E', assetClass: 'ABD Hisse/ETF' },
};

async function fetchBenchmarkReturn(benchmark: string, days: number): Promise<number> {
  try {
    const info = BENCHMARK_TICKERS[benchmark];
    if (!info) return 0;
    const history = await api.getPriceHistory(info.ticker, days, info.assetClass);
    if (!history || history.length < 2) return 0;
    const first = history[0].price;
    const last = history[history.length - 1].price;
    if (!first) return 0;
    return (last - first) / first * 100;
  } catch {
    return 0;
  }
}

export default function DashboardApp() {
  const { token, setToken } = useAuth();
  const navigate = useNavigate();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [performanceHistory, setPerformanceHistory] = useState<any[]>([]);
  const [exchangeRates, setExchangeRates] = useState<{ usd_rate: number; eur_rate: number; gbp_rate?: number }>({ usd_rate: 35.0, eur_rate: 38.0 });
  const [performanceMetrics, setPerformanceMetrics] = useState<{ twrr: number; volatility: number; max_drawdown: number; netAlpha?: number } | null>(null);
  const [performanceDays, setPerformanceDays] = useState<90 | 180 | 365 | 730>(90);

  // Load and persist settings state from local storage
  const [settings, setSettings] = useState<UserSettings>(() => {
    try {
      const saved = localStorage.getItem('lucrum_settings_v1');
      return saved ? JSON.parse(saved) : INITIAL_SETTINGS;
    } catch {
      return INITIAL_SETTINGS;
    }
  });

  const [activeTab, setActiveTab] = useState<ActiveTab>('portfolio');
  const [selectedSymbolFromSearch, setSelectedSymbolFromSearch] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);

      // Fetch rates + portfolio in parallel — show UI as soon as both arrive
      const [rates, portfolio] = await Promise.all([
        api.getExchangeRates(),
        api.getPortfolio(),
      ]);
      setExchangeRates({ usd_rate: rates.usd_rate, eur_rate: rates.eur_rate, gbp_rate: rates.gbp_rate });

      const mapped: Holding[] = portfolio.holdings.map((pos) => {
        const marketAsset = MARKET_ASSETS.find(
          (a) => a.symbol.toUpperCase() === pos.ticker.toUpperCase()
        );

        let category: AssetCategory = 'Equity';
        if (pos.asset_class === 'Kripto') {
          category = 'Crypto';
        } else if (pos.asset_class === 'Nakit' || pos.asset_class === 'Cash') {
          category = 'Cash';
        } else if (pos.asset_class === 'FixedIncome' || pos.asset_class === 'Emtia' || pos.asset_class === 'Bonds' || pos.ticker === 'US10Y') {
          category = 'FixedIncome';
        }

        // 1. Calculate purchase price in settings baseCurrency using historical exchange rate.
        // Backend returns invested_tly which uses the USD/TRY rate at the actual buy date.
        // This is more accurate than converting with today's rate.
        let avgBuyPrice: number;
        if (pos.invested_tly != null && pos.quantity > 0) {
          const costTRY = pos.invested_tly;
          avgBuyPrice = settings.baseCurrency === 'TRY'
            ? costTRY / pos.quantity
            : convertCurrency(costTRY / pos.quantity, 'TRY', settings.baseCurrency, rates);
        } else {
          avgBuyPrice = convertCurrency(pos.buy_price, pos.buy_currency, settings.baseCurrency, rates);
        }

        // 2. Calculate current price in settings baseCurrency
        let currentPrice = 0;
        if (pos.current_price !== null && pos.current_price !== undefined) {
          const priceCurrency = pos.asset_class === 'Kripto' ? 'USD' : pos.buy_currency;
          currentPrice = convertCurrency(pos.current_price, priceCurrency, settings.baseCurrency, rates);
        } else {
          currentPrice = avgBuyPrice;
        }

        return {
          id: String(pos.id),
          symbol: pos.ticker,
          name: marketAsset ? marketAsset.name : pos.ticker,
          category: category,
          sector: marketAsset ? marketAsset.sector : (pos.asset_class || 'Other'),
          shares: pos.quantity,
          avgBuyPrice: avgBuyPrice,
          currentPrice: currentPrice,
          // Modül-level cache'den al; yoksa MARKET_ASSETS beta ya da 5.0
          riskScore: _riskCache[pos.ticker] ?? (marketAsset ? marketAsset.beta * 4 : 5.0),
          assetClass: pos.asset_class,
        };
      });

      setHoldings(mapped);
      setLoading(false); // Show UI now — don't wait for performance chart

      // Risk skorlarını arka planda güncelle (yfinance beta, 7 gün SQLite cache'li)
      api.getRiskScores()
        .then((scores) => {
          if (!scores || Object.keys(scores).length === 0) return;
          Object.assign(_riskCache, scores); // modül cache'e kaydet
          setHoldings(prev => prev.map(h => {
            const s = _riskCache[h.symbol];
            return s != null ? { ...h, riskScore: s } : h;
          }));
        })
        .catch(() => {});

      // Load performance history in background (non-blocking)
      api.getPerformance(performanceDays, settings.baseCurrency)
        .then(async (performance) => {
          setPerformanceHistory(performance.history);
          const benchmarkReturn = await fetchBenchmarkReturn(settings.benchmark, performanceDays);
          const netAlpha = performance.twrr - benchmarkReturn;
          setPerformanceMetrics({ twrr: performance.twrr, volatility: performance.volatility, max_drawdown: performance.max_drawdown, netAlpha });
        })
        .catch((err) => console.error('Performance load failed:', err));

    } catch (err) {
      console.error('Error loading backend data:', err);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      loadData();
    }
  }, [token]);

  useEffect(() => {
    localStorage.setItem('lucrum_settings_v1', JSON.stringify(settings));
  }, [settings]);

  // Effect A: SADECE benchmark değişince — sadece netAlpha'yı yeniden hesapla (TWRR'ı tekrar çekme)
  useEffect(() => {
    if (!performanceMetrics) return;
    let cancelled = false;
    fetchBenchmarkReturn(settings.benchmark, performanceDays)
      .then((benchmarkReturn) => {
        if (cancelled) return;
        setPerformanceMetrics(prev => prev ? { ...prev, netAlpha: prev.twrr - benchmarkReturn } : prev);
      });
    return () => { cancelled = true; };
  }, [settings.benchmark, performanceDays]);

  // Effect C: baseCurrency değişince tüm veriyi yeniden yükle (fiyat dönüşümleri değişir)
  const prevBaseCurrencyRef = useRef(settings.baseCurrency);
  useEffect(() => {
    if (prevBaseCurrencyRef.current === settings.baseCurrency) return;
    prevBaseCurrencyRef.current = settings.baseCurrency;
    if (holdings.length > 0) loadData();
  }, [settings.baseCurrency]); // eslint-disable-line react-hooks/exhaustive-deps

  // Effect B: performanceDays değişince tam refetch (hem TWRR hem benchmark)
  useEffect(() => {
    if (holdings.length === 0) return;
    let cancelled = false;
    api.getPerformance(performanceDays, settings.baseCurrency)
      .then(async (performance) => {
        if (cancelled) return;
        const benchmarkReturn = await fetchBenchmarkReturn(settings.benchmark, performanceDays);
        if (cancelled) return;
        setPerformanceHistory(performance.history);
        setPerformanceMetrics({
          twrr: performance.twrr,
          volatility: performance.volatility,
          max_drawdown: performance.max_drawdown,
          netAlpha: performance.twrr - benchmarkReturn,
        });
      })
      .catch(err => console.error('Performance reload failed:', err));
    return () => { cancelled = true; };
  }, [performanceDays]); // settings.benchmark stale closure yok çünkü fetchBenchmarkReturn closure'ı her render'da taze

  // Recalculate portfolio metrics dynamically in real-time
  const portfolioMetrics = calculatePortfolio(holdings);

  // Core callback: add/update transactions or custom holdings
  const handleAddHolding = async (newHolding: Omit<Holding, 'id'>) => {
    try {
      // Eğer holding'in mevcut assetClass'ı varsa (edit akışında) doğrudan kullan
      let assetClass = newHolding.assetClass || 'ABD Hisse/ETF';
      if (!newHolding.assetClass) {
        if (newHolding.category === 'Crypto') {
          assetClass = 'Kripto';
        } else if (newHolding.category === 'Cash') {
          assetClass = 'Nakit';
        } else if (newHolding.category === 'FixedIncome') {
          assetClass = 'Emtia';
          if (newHolding.symbol === 'US10Y') {
            assetClass = 'FixedIncome';
          }
        } else {
          const sym = newHolding.symbol.toUpperCase();
          if (sym.endsWith('.IS') || sym.endsWith('.E1') ||
            ['THYAO', 'ASELS', 'EREGL', 'GARAN', 'TUPRS', 'KCHOL', 'GESAN', 'PATEK', 'GWIND', 'CWENE', 'SDTTR',
              'AKBNK', 'ISCTR', 'SAHOL', 'SISE', 'BIMAS', 'MGROS', 'FROTO', 'TOASO', 'ARCLK', 'TCELL',
              'PGSUS', 'TAVHL', 'EKGYO', 'PETKM', 'YKBNK', 'HALKB', 'VAKBN', 'KOZAL', 'KOZAA', 'ENKAI'].includes(sym)) {
            assetClass = 'BIST Hissesi';
          } else if (['JET', 'SAS', 'TI3', 'YAS', 'KZL', 'AFA', 'AFT', 'GO2', 'GO3', 'GO4', 'YAY', 'AFV', 'BIH', 'HBU'].includes(sym)) {
            assetClass = 'TEFAS Fonu';
          } else {
            assetClass = 'ABD Hisse/ETF';
          }
        }
      }

      let buyCurrency = 'USD';
      if (newHolding.category === 'Cash') {
        buyCurrency = newHolding.symbol.toUpperCase();
      } else if (assetClass === 'BIST Hissesi' || assetClass === 'TEFAS Fonu' || newHolding.symbol === 'TRY') {
        buyCurrency = 'TRY';
      } else if (newHolding.symbol === 'EUR') {
        buyCurrency = 'EUR';
      } else if (newHolding.symbol === 'GBP') {
        buyCurrency = 'GBP';
      }

      const buyPriceInNative = newHolding.category === 'Cash'
        ? 1.0
        : convertCurrency(newHolding.avgBuyPrice, settings.baseCurrency, buyCurrency, exchangeRates);
      const todayStr = new Date().toISOString().split('T')[0];

      await api.addPosition({
        ticker: newHolding.symbol.toUpperCase(),
        asset_class: assetClass,
        quantity: newHolding.shares,
        buy_price: buyPriceInNative,
        buy_date: todayStr,
        buy_currency: buyCurrency,
      });

      await loadData();
    } catch (err: any) {
      console.error('Error adding holding to backend:', err);
      setErrorMessage(err.message || 'İşlem başarısız.');
      setTimeout(() => setErrorMessage(null), 5000);
    }
  };

  const handleDeleteHolding = async (id: string) => {
    try {
      await api.deletePosition(id);
      await loadData();
    } catch (err: any) {
      console.error('Error deleting holding from backend:', err);
      setErrorMessage(err.message || 'İşlem başarısız.');
      setTimeout(() => setErrorMessage(null), 5000);
    }
  };

  const handleEditHolding = async (
    originalId: string,
    originalHolding: Omit<import('./types').Holding, 'id'>,
    newShares: number,
    newAvgPrice: number
  ) => {
    try {
      await api.deletePosition(originalId);
      if (newShares > 0) {
        await handleAddHolding({ ...originalHolding, shares: newShares, avgBuyPrice: newAvgPrice });
      } else {
        await loadData();
      }
    } catch (err) {
      console.error('Error editing holding:', err);
    }
  };

  const handleUpdateSettings = (newSettings: Partial<UserSettings>) => {
    setSettings((prev) => ({ ...prev, ...newSettings }));
  };

  const handleResetPortfolio = async () => {
    try {
      setLoading(true);
      await api.resetPortfolio();
      setSettings(INITIAL_SETTINGS);
      await loadData();
      setActiveTab('portfolio');
    } catch (err) {
      console.error('Error resetting database:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    api.logout().catch(() => {});
    setToken(null);
    setHoldings([]);
    setPerformanceHistory([]);
    setPerformanceMetrics(null);
    setActiveTab('portfolio');
    navigate('/');
  };

  // Search Select Asset logic - transitions to markets view and highlights the selected instrument
  const handleSearchSelectAsset = (symbol: string) => {
    setSelectedSymbolFromSearch(symbol);
    setActiveTab('markets');
  };

  const t = useT(settings?.language || 'tr');

  if (loading && holdings.length === 0) {
    return (
      <div className="min-h-screen bg-[#F9F7F2] flex flex-col items-center justify-center font-sans">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
          className="w-10 h-10 border-4 border-[#8C9A86] border-t-transparent rounded-full mb-4"
        />
        <p className="text-xs font-bold text-[#9E958C] uppercase tracking-wider">{t.calibrating}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F7F2] text-[#4A443F] font-sans antialiased selection:bg-[#8C9A86]/30 selection:text-[#4A443F]">

      {/* Dynamic Sidebar navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        settings={settings}
      />

      {/* Global Header Search & notification bar */}
      <Header onSearchSelectAsset={handleSearchSelectAsset} settings={settings} exchangeRates={exchangeRates} />

      {/* Main viewport area */}
      <main className="ml-64 mt-16 p-8 h-[calc(100vh-64px)] overflow-y-auto custom-scrollbar">
        <div className="max-w-7xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {activeTab === 'portfolio' && (
                <DashboardView
                  metrics={portfolioMetrics}
                  onAddHolding={handleAddHolding}
                  onDeleteHolding={handleDeleteHolding}
                  onEditHolding={handleEditHolding}
                  settings={settings}
                  performanceHistory={performanceHistory}
                  exchangeRates={exchangeRates}
                  performanceMetrics={performanceMetrics}
                  performanceDays={performanceDays}
                  onPerformanceDaysChange={setPerformanceDays}
                />
              )}

              {activeTab === 'analytics' && (
                <AnalyticsView
                  holdings={portfolioMetrics.holdings}
                  totalValue={portfolioMetrics.totalValue}
                  settings={settings}
                />
              )}

              {activeTab === 'risk' && (
                <RiskView
                  holdings={portfolioMetrics.holdings}
                  settings={settings}
                />
              )}

              {activeTab === 'markets' && (
                <MarketsView
                  selectedSymbolFromSearch={selectedSymbolFromSearch}
                  setSelectedSymbolFromSearch={setSelectedSymbolFromSearch}
                  onAddHoldingFromMarket={handleAddHolding}
                  settings={settings}
                  exchangeRates={exchangeRates}
                />
              )}

              {activeTab === 'news' && (
                <NewsView
                  holdings={portfolioMetrics.holdings}
                  settings={settings}
                />
              )}

              {activeTab === 'settings' && (
                <SettingsView
                  settings={settings}
                  onUpdateSettings={handleUpdateSettings}
                  onResetPortfolio={handleResetPortfolio}
                  onLogout={handleLogout}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      {errorMessage && (
        <div id="dashboard-error-toast" className="fixed bottom-6 right-6 bg-[#B5836F] text-white border border-[#A2715F] rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3 z-50 font-semibold text-sm">
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
