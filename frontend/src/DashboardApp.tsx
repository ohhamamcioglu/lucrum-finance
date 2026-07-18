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
import LiabilitiesView from './components/LiabilitiesView';

import { Holding, ActiveTab, UserSettings, AssetCategory, Liability } from './types';
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
  // performanceHistory/Metrics arka planda yükleniyor (bkz. loadData) — bu bayrak olmadan
  // DashboardView, yükleme sırasında "Henüz veri birikmedi" mesajını gerçekten boş bir
  // portföyle karıştırıyordu (aynı [] başlangıç değeri her iki durumda da geçerli).
  const [performanceLoading, setPerformanceLoading] = useState<boolean>(true);

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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  // Aynı sembolü paylaşan farklı varlık sınıflarını (ör. TEFAS fonu vs ABD ETF'i)
  // ayırt edebilmek için — bkz. MarketsView'daki kullanım notu.
  const [selectedAssetClassFromSearch, setSelectedAssetClassFromSearch] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const showError = (message: string) => {
    setErrorMessage(message);
    setTimeout(() => setErrorMessage(null), 5000);
  };
  const [liabilities, setLiabilities] = useState<Liability[]>([]);

  const loadLiabilities = async () => {
    try {
      const rows = await api.getLiabilities();
      setLiabilities(rows.map(r => ({
        id: r.id,
        name: r.name,
        liability_type: r.liability_type as Liability['liability_type'],
        amount: r.amount,
        currency: r.currency as Liability['currency'],
        due_date: r.due_date,
        interest_rate: r.interest_rate,
      })));
    } catch (err) {
      console.error('Error loading liabilities:', err);
    }
  };

  const handleAddLiability = async (item: Omit<Liability, 'id'>) => {
    await api.addLiability(item);
    await loadLiabilities();
  };

  const handleEditLiability = async (id: number, item: Omit<Liability, 'id'>) => {
    await api.updateLiability(id, item);
    await loadLiabilities();
  };

  const handleDeleteLiability = async (id: number) => {
    try {
      await api.deleteLiability(id);
      await loadLiabilities();
    } catch (err: any) {
      console.error('Error deleting liability:', err);
      showError(err.message || 'İşlem başarısız.');
    }
  };

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

        // 1 & 2. Backend artık invested_{try,usd,eur,gbp} ve current_value_{try,usd,eur,gbp}
        // alanlarını HER para birimi için kendi doğru kuruyla hesaplayıp döndürüyor
        // (yatırım = alım tarihi kuru, güncel değer = bugünün kuru — bkz. services.py
        // calculate_portfolio). Burada TL üzerinden bugünün kuruyla ek bir çevrim YAPMIYORUZ;
        // eskiden bu double-conversion, fiyatı hiç değişmemiş yabancı para pozisyonlarında bile
        // sahte kâr/zarar üretiyordu. convertCurrency'e sadece backend değeri eksikse (örn. fiyat
        // hiç çekilememişse) geriye dönük uyumluluk için düşüyoruz.
        const investedByCurrency: Record<string, number | null | undefined> = {
          TRY: pos.invested_tly, USD: pos.invested_usd, EUR: pos.invested_eur, GBP: pos.invested_gbp,
        };
        const currentValueByCurrency: Record<string, number | null | undefined> = {
          TRY: pos.current_value_tly, USD: pos.current_value_usd, EUR: pos.current_value_eur, GBP: pos.current_value_gbp,
        };

        const investedInBase = investedByCurrency[settings.baseCurrency];
        const avgBuyPrice = investedInBase != null && pos.quantity > 0
          ? investedInBase / pos.quantity
          : convertCurrency(pos.buy_price, pos.buy_currency, settings.baseCurrency, rates);

        const currentValueInBase = currentValueByCurrency[settings.baseCurrency];
        let currentPrice: number;
        if (currentValueInBase != null && pos.quantity > 0) {
          currentPrice = currentValueInBase / pos.quantity;
        } else if (pos.current_price !== null && pos.current_price !== undefined) {
          const priceCurrency = pos.price_currency || (pos.asset_class === 'Kripto' ? 'USD' : pos.buy_currency);
          currentPrice = convertCurrency(pos.current_price, priceCurrency, settings.baseCurrency, rates);
        } else {
          currentPrice = avgBuyPrice;
        }

        return {
          id: String(pos.id),
          symbol: pos.ticker,
          name: marketAsset ? marketAsset.name : pos.ticker,
          category: category,
          // marketAsset.sector zaten İngilizce (Technology, Cryptocurrency vb.) — statik listede
          // olmayan pozisyonlar için ham asset_class'a düşerken aynı taksonomiye normalize et,
          // yoksa örn. 'Kripto' (DB) ve 'Cryptocurrency' (statik liste) grafikte iki ayrı dilim olur.
          sector: marketAsset ? marketAsset.sector : (pos.asset_class === 'Kripto' ? 'Cryptocurrency' : (pos.asset_class || 'Other')),
          shares: pos.quantity,
          avgBuyPrice: avgBuyPrice,
          currentPrice: currentPrice,
          // Modül-level cache'den al; yoksa MARKET_ASSETS beta ya da 5.0
          riskScore: _riskCache[pos.ticker] ?? (marketAsset ? marketAsset.beta * 4 : 5.0),
          assetClass: pos.asset_class,
          changePct: pos.change_pct ?? null,
          buyDate: typeof pos.buy_date === 'string' ? pos.buy_date : String(pos.buy_date),
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
        .catch((err) => console.warn('Risk score refresh failed:', err));

      // Load performance history in background (non-blocking)
      setPerformanceLoading(true);
      api.getPerformance(performanceDays, settings.baseCurrency)
        .then(async (performance) => {
          setPerformanceHistory(performance.history);
          const benchmarkReturn = await fetchBenchmarkReturn(settings.benchmark, performanceDays);
          const netAlpha = performance.twrr - benchmarkReturn;
          setPerformanceMetrics({ twrr: performance.twrr, volatility: performance.volatility, max_drawdown: performance.max_drawdown, netAlpha });
        })
        .catch((err) => console.error('Performance load failed:', err))
        .finally(() => setPerformanceLoading(false));

    } catch (err) {
      console.error('Error loading backend data:', err);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      loadData();
      loadLiabilities();
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
    setPerformanceLoading(true);
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
      .catch(err => console.error('Performance reload failed:', err))
      .finally(() => { if (!cancelled) setPerformanceLoading(false); });
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

      // newHolding.avgBuyPrice artık DashboardView'daki form alanından zaten native para
      // biriminde geliyor (settings.baseCurrency değil) — burada ek bir çevrim YAPILMAZ.
      // Aksi halde geçmiş bir alım tarihi için bugünün kuruyla yanlış bir native fiyat üretilirdi.
      const buyPriceInNative = newHolding.category === 'Cash' ? 1.0 : newHolding.avgBuyPrice;
      const todayStr = new Date().toISOString().split('T')[0];
      // Kullanıcının formda girdiği alım tarihi kullanılır; edit/top-up akışında (handleEditHolding)
      // orijinal pozisyonun buyDate'i buraya zaten taşınmış olur — yoksa bugüne düşer.
      const buyDateStr = newHolding.buyDate || todayStr;

      await api.addPosition({
        ticker: newHolding.symbol.toUpperCase(),
        asset_class: assetClass,
        quantity: newHolding.shares,
        buy_price: buyPriceInNative,
        buy_date: buyDateStr,
        buy_currency: buyCurrency,
      });

      await loadData();
    } catch (err: any) {
      console.error('Error adding holding to backend:', err);
      showError(err.message || 'İşlem başarısız.');
    }
  };

  const handleDeleteHolding = async (id: string) => {
    try {
      await api.deletePosition(id);
      await loadData();
    } catch (err: any) {
      console.error('Error deleting holding from backend:', err);
      showError(err.message || 'İşlem başarısız.');
    }
  };

  const handleEditHolding = async (
    originalId: string,
    _originalHolding: Omit<import('./types').Holding, 'id'>,
    newShares: number,
    newAvgPrice: number,
    deltaQuantity: number,
    deltaPrice: number
  ) => {
    try {
      if (newShares > 0) {
        // Pozisyonu YERİNDE güncelle (sil+yeniden-ekle DEĞİL) — orijinal alım tarihi ve
        // mevcut işlem geçmişi korunur. Top-up/kısmi satış, bugünün tarihiyle GERÇEK bir
        // işlem (BUY/SELL) olarak ayrıca eklenir, eskiler silinmez.
        await api.updatePosition(originalId, {
          quantity: newShares,
          buy_price: newAvgPrice,
          delta_quantity: deltaQuantity,
          delta_price: deltaPrice,
        });
      } else {
        // Pozisyon tamamen kapatılıyor — gerçek çıkış fiyatıyla SELL kaydı bırakılır.
        await api.deletePosition(originalId, deltaPrice);
      }
      await loadData();
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
    api.logout().catch((err) => console.warn('Server-side logout failed, continuing with local logout:', err));
    setToken(null);
    setHoldings([]);
    setPerformanceHistory([]);
    setPerformanceMetrics(null);
    setActiveTab('portfolio');
    navigate('/');
  };

  // Search Select Asset logic - transitions to markets view and highlights the selected instrument
  const handleSearchSelectAsset = (symbol: string, assetClass: string) => {
    setSelectedSymbolFromSearch(symbol);
    setSelectedAssetClassFromSearch(assetClass);
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
        mobileOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Global Header Search & notification bar */}
      <Header
        onSearchSelectAsset={handleSearchSelectAsset}
        settings={settings}
        exchangeRates={exchangeRates}
        onMenuClick={() => setMobileMenuOpen(true)}
      />

      {/* Main viewport area.
          Not: eskiden "mt-16 h-[calc(100vh-64px)]" idi — main'in margin-top'ı,
          üst kapsayıcıda onu engelleyecek bir padding/border/overflow olmadığı için
          kapsayıcının kendi üst kenarıyla "collapse" oluyordu. Görünürde hiçbir şey
          taşmıyor gibi göründüğü halde belge (html/body) 64px daha uzun ölçülüyor ve
          hem mobilde hem masaüstünde işlevsiz bir dikey scrollbar çıkıyordu. margin
          yerine main'in KENDİ padding'i (pt-*) kullanılınca collapse hiç olmuyor.

          h-screen (100vh) yerine h-dvh (100dvh) kullanılıyor — mobil tarayıcılarda
          100vh, adres çubuğu gizliyken ulaşılabilecek EN BÜYÜK görünür alanı esas
          alır; adres çubuğu görünürken gerçek görünür alan daha küçüktür. Bu yüzden
          main'in kutusu gerçek ekrandan daha uzun ölçülüp en alttaki içerik (son
          pozisyonlar) normal kaydırmayla erişilemez hale geliyordu. 100dvh tarayıcı
          arayüzündeki değişikliklere göre dinamik olarak güncellenir, bu sorunu
          ortadan kaldırır. h-screen'i de bırakıyoruz — dvh'yi desteklemeyen eski
          tarayıcılarda yedek olarak kalır. */}
      {/* pb-24 (mobil): dvh düzeltmesi tarayıcının üstteki adres çubuğunu hesaba
          katıyor, ama alttaki gezinme çubuğu/home-indicator bazı mobil
          tarayıcılarda içeriğin üzerine bindirilmiş (overlay) şekilde duruyor —
          bu, dvh'ye yansımıyor. Bol bir alt tampon + güvenli alan payı, son
          öğenin bu arayüzün arkasında kalmasını engelliyor. */}
      <main className="ml-0 md:ml-64 h-screen h-dvh overflow-y-auto custom-scrollbar px-4 md:px-8 pt-20 md:pt-24 md:pb-8 [padding-bottom:max(6rem,env(safe-area-inset-bottom))] md:[padding-bottom:2rem]">
        <div className="max-w-7xl mx-auto">
          <AnimatePresence mode="popLayout" initial={false}>
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
                  performanceLoading={performanceLoading}
                  performanceDays={performanceDays}
                  onPerformanceDaysChange={setPerformanceDays}
                  liabilities={liabilities}
                />
              )}

              {activeTab === 'liabilities' && (
                <LiabilitiesView
                  liabilities={liabilities}
                  settings={settings}
                  exchangeRates={exchangeRates}
                  onAddLiability={handleAddLiability}
                  onEditLiability={handleEditLiability}
                  onDeleteLiability={handleDeleteLiability}
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
                  selectedAssetClassFromSearch={selectedAssetClassFromSearch}
                  onAddHoldingFromMarket={handleAddHolding}
                  settings={settings}
                  exchangeRates={exchangeRates}
                  onError={showError}
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
                  currentPositionCount={portfolioMetrics.holdings.length}
                  onError={showError}
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
