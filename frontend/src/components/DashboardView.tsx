import { useState, FormEvent, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  TrendingUp, Bolt, Plus, Trash2, X, Wallet2, AlertCircle,
  Pencil, ChevronUp, ChevronDown, ChevronsUpDown,
} from 'lucide-react';
import { Holding, AssetCategory, UserSettings, Liability } from '../types';
import { formatCurrency, MARKET_ASSETS, convertCurrency } from '../utils';
import { useT } from '../i18n';
import { api, BASE_URL } from '../services/api';

type SortKey = 'symbol' | 'allocation' | 'value' | 'pl' | 'plPct' | 'risk';
type SortDir = 'asc' | 'desc';

type EnrichedHolding = Holding & {
  value: number;
  cost: number;
  unrealizedPL: number;
  unrealizedPLPercent: number;
  allocationPercent: number;
};

interface DashboardViewProps {
  metrics: {
    totalValue: number;
    totalCost: number;
    unrealizedPL: number;
    unrealizedPLPercent: number;
    portfolioRiskScore: number;
    categoryAllocations: Array<{ category: AssetCategory; value: number; percent: number }>;
    detailedAllocations: Array<{ category: string; value: number; percent: number }>;
    holdings: EnrichedHolding[];
    cashAmount: number;
  };
  onAddHolding: (holding: Omit<Holding, 'id'>) => void;
  onDeleteHolding: (id: string) => void;
  onEditHolding: (
    originalId: string,
    originalHolding: Omit<Holding, 'id'>,
    newShares: number,
    newAvgPrice: number,
    deltaQuantity: number,
    deltaPrice: number
  ) => void;
  settings: UserSettings;
  performanceHistory?: any[];
  exchangeRates: { usd_rate: number; eur_rate: number; gbp_rate?: number };
  performanceMetrics?: { twrr: number; volatility: number; max_drawdown: number; netAlpha?: number } | null;
  performanceDays?: 90 | 180 | 365 | 730;
  onPerformanceDaysChange?: (days: 90 | 180 | 365 | 730) => void;
  liabilities?: Liability[];
}

export default function DashboardView({
  metrics,
  onAddHolding,
  onDeleteHolding,
  onEditHolding,
  settings,
  performanceHistory = [],
  exchangeRates,
  performanceMetrics = null,
  performanceDays = 90,
  onPerformanceDaysChange,
  liabilities = [],
}: DashboardViewProps) {
  const t = useT(settings.language);

  // ── Add modal ────────────────────────────────────────────────────
  const [showAddModal, setShowAddModal] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState<AssetCategory>('Equity');
  const [newSector, setNewSector] = useState('Technology');
  const [newShares, setNewShares] = useState(10);
  const [newPrice, setNewPrice] = useState(150);
  const [newRisk, setNewRisk] = useState(5.0);
  const [newBuyDate, setNewBuyDate] = useState(() => new Date().toISOString().split('T')[0]);

  // Autocomplete suggestions states
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Modal chart states
  const [modalHistory, setModalHistory] = useState<Array<{ date: string; price: number }>>([]);
  const [loadingModalHistory, setLoadingModalHistory] = useState(false);

  // Asset class tracker
  const [newAssetClass, setNewAssetClass] = useState('ABD Hisse/ETF');
  const symbolBlurTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // "Alım Fiyatı" alanı her zaman varlığın KENDİ native para biriminde girilir (settings.baseCurrency
  // değil) — geçmiş bir alım tarihi girildiğinde bugünün kuruyla yanlış çevrim yapılmasını önler.
  const nativeBuyCurrency = newCategory === 'Cash'
    ? (newSymbol || 'TRY').toUpperCase()
    : (newAssetClass === 'BIST Hissesi' || newAssetClass === 'TEFAS Fonu') ? 'TRY' : 'USD';

  // Category change side-effects
  useEffect(() => {
    setModalHistory([]);
    if (newCategory === 'Cash') {
      const defaultCur = settings.baseCurrency || 'USD';
      setNewSymbol(defaultCur);
      setNewName(settings.language === 'tr' ? `${defaultCur} Nakit` : `${defaultCur} Cash`);
      setNewSector('Cash');
      setNewRisk(0.0);
      setNewPrice(1.0);
      setNewAssetClass('Nakit');
    } else if (newCategory === 'FixedIncome') {
      setNewSymbol('');
      setNewName('');
      setNewSector('Government');
      setNewRisk(1.5);
      setNewPrice(100.0);
      setNewAssetClass('FixedIncome');
    } else if (newCategory === 'Crypto') {
      setNewSymbol('');
      setNewName('');
      setNewSector('Cryptocurrency');
      setNewRisk(9.0);
      setNewPrice(1.0);
      setNewAssetClass('Kripto');
    } else { // Equity
      setNewSymbol('');
      setNewName('');
      setNewSector('Technology');
      setNewRisk(5.5);
      setNewPrice(150.0);
      setNewAssetClass('ABD Hisse/ETF');
    }
  }, [newCategory, settings.language, settings.baseCurrency]);

  // Debounced search suggestions fetch
  useEffect(() => {
    if (newCategory === 'Cash' || !newSymbol || newSymbol.trim().length === 0) {
      setSuggestions([]);
      return;
    }

    const delayDebounceFn = setTimeout(async () => {
      setLoadingSuggestions(true);
      try {
        const response = await fetch(`${BASE_URL}/api/assets/search?query=${encodeURIComponent(newSymbol)}`);
        if (response.ok) {
          const data = await response.json();
          setSuggestions(data);
        }
      } catch (error) {
        console.error('Error fetching suggestions:', error);
      } finally {
        setLoadingSuggestions(false);
      }
    }, 300);

    return () => clearTimeout(delayDebounceFn);
  }, [newSymbol, newCategory]);

  const fetchModalHistory = async (symbol: string, assetClass: string) => {
    if (newCategory === 'Cash' || !symbol) {
      setModalHistory([]);
      return;
    }
    setLoadingModalHistory(true);
    try {
      const history = await api.getPriceHistory(symbol, 30, assetClass);
      setModalHistory(history);
    } catch (error) {
      console.error('Error fetching modal chart history:', error);
      setModalHistory([]);
    } finally {
      setLoadingModalHistory(false);
    }
  };

  const handleSelectSuggestion = async (item: any) => {
    setNewSymbol(item.symbol);
    setNewName(item.name);
    setNewCategory(item.category);
    setNewAssetClass(item.asset_class);
    setNewSector(item.sector);
    setNewRisk(item.riskScore);
    setShowSuggestions(false);
    fetchModalHistory(item.symbol, item.asset_class);

    try {
      const assetClass = item.asset_class;
      const res = await fetch(`${BASE_URL}/api/prices/${encodeURIComponent(item.symbol)}?asset_class=${encodeURIComponent(assetClass)}`);
      if (res.ok) {
        const priceData = await res.json();
        if (priceData && priceData.price) {
          // Fiyat, varlığın KENDİ native para biriminde tutulur (backend'in döndürdüğü currency
          // alanına göre) — settings.baseCurrency'ye çevrilmez. Aksi halde geçmiş bir alım
          // tarihi girildiğinde, girilen fiyat bugünün kuruyla yanlış native tutara dönüşür.
          setNewPrice(Number(priceData.price.toFixed(4)));
        }
      }
    } catch (error) {
      console.error('Error fetching price for suggestion:', error);
    }
  };

  const handleSymbolBlur = async () => {
    if (symbolBlurTimerRef.current) clearTimeout(symbolBlurTimerRef.current);
    symbolBlurTimerRef.current = setTimeout(async () => {
      symbolBlurTimerRef.current = null;
      if (newCategory === 'Cash' || !newSymbol || newSymbol.trim().length === 0) return;
      
      let assetClass = 'ABD Hisse/ETF';
      if (newCategory === 'Crypto') {
        assetClass = 'Kripto';
      } else if (newCategory === 'FixedIncome') {
        const sym = newSymbol.toUpperCase();
        if (['JET', 'SAS', 'TI3', 'YAS', 'KZL', 'AFA', 'AFT', 'GO2', 'GO3', 'GO4', 'YAY', 'AFV', 'BIH', 'HBU'].includes(sym) || sym.length === 3) {
          assetClass = 'TEFAS Fonu';
        } else {
          assetClass = 'FixedIncome';
        }
      } else if (newCategory === 'Equity') {
        const sym = newSymbol.toUpperCase();
        if (sym.endsWith('.IS')) {
          assetClass = 'BIST Hissesi';
        }
      }

      // 1. Resolve exact asset class and metadata from search endpoint (lightning fast)
      try {
        const searchRes = await fetch(`${BASE_URL}/api/assets/search?query=${encodeURIComponent(newSymbol)}`);
        if (searchRes.ok) {
          const searchData = await searchRes.json();
          const match = searchData.find((item: any) => item.symbol.toUpperCase() === newSymbol.toUpperCase());
          if (match) {
            assetClass = match.asset_class;
            if (match.name) setNewName(match.name);
            if (match.sector) setNewSector(match.sector);
            if (match.riskScore !== undefined) setNewRisk(match.riskScore);
          }
        }
      } catch (error) {
        console.error('Error matching symbol from search:', error);
      }

      setNewAssetClass(assetClass);

      // 2. Fetch history, overview, and price in parallel
      const fetchOverview = async () => {
        try {
          const res = await fetch(`${BASE_URL}/api/assets/${encodeURIComponent(newSymbol)}/overview?asset_class=${encodeURIComponent(assetClass)}`);
          if (res.ok) {
            const data = await res.json();
            if (data) {
              if (data.name && data.name !== newSymbol) setNewName(data.name);
              if (data.sector && data.sector !== 'N/A') setNewSector(data.sector);
            }
          }
        } catch (err) {
          console.error('Error fetching overview on blur:', err);
        }
      };

      const fetchPrice = async () => {
        try {
          const res = await fetch(`${BASE_URL}/api/prices/${encodeURIComponent(newSymbol)}?asset_class=${encodeURIComponent(assetClass)}`);
          if (res.ok) {
            const priceData = await res.json();
            if (priceData && priceData.price) {
              // Native para biriminde tutulur — bkz. handleSelectSuggestion'daki not.
              setNewPrice(Number(priceData.price.toFixed(4)));
            }
          }
        } catch (err) {
          console.error('Error fetching price on blur:', err);
        }
      };

      Promise.all([
        fetchModalHistory(newSymbol, assetClass),
        fetchOverview(),
        fetchPrice()
      ]);
    }, 250);
  };

  // ── Edit modal ───────────────────────────────────────────────────
  const [editingHolding, setEditingHolding] = useState<EnrichedHolding | null>(null);
  const [editMode, setEditMode] = useState<'increase' | 'decrease'>('increase');
  const [editQty, setEditQty] = useState(0);
  const [editPrice, setEditPrice] = useState(0);

  // ── Detail modal ──────────────────────────────────────────────────
  const [selectedAssetForDetail, setSelectedAssetForDetail] = useState<EnrichedHolding | null>(null);
  const [detailHistory, setDetailHistory] = useState<Array<{ date: string; price: number }>>([]);
  const [detailOverview, setDetailOverview] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (!selectedAssetForDetail) {
      setDetailHistory([]);
      setDetailOverview(null);
      return;
    }

    // Hızlı varlık değişiminde (örn. A'ya tıkla, sonuç gelmeden B'ye tıkla) daha yavaş
    // giden eski istek (ör. TEFAS/BIST) geç dönüp geçerli varlığın grafiğini/analiz
    // panelini yanlış veriyle eziyordu — bu bayrak, o anki isteğin hâlâ güncel
    // seçili varlığa mı ait olduğunu kontrol eder, değilse sonucu uygulamaz.
    let cancelled = false;
    const requestedSymbol = selectedAssetForDetail.symbol;

    const fetchDetailData = async () => {
      // Nakit pozisyonlar için fiyat geçmişi veya analiz çekme
      if (selectedAssetForDetail.category === 'Cash') {
        setDetailHistory([]);
        setDetailOverview(null);
        setLoadingDetail(false);
        return;
      }
      setLoadingDetail(true);
      try {
        const assetClass = selectedAssetForDetail.assetClass || 'ABD Hisse/ETF';
        const [history, overview] = await Promise.all([
          api.getPriceHistory(requestedSymbol, 90, assetClass),
          api.getAssetOverview(requestedSymbol, assetClass),
        ]);
        if (cancelled) return;
        setDetailHistory(history);
        setDetailOverview(overview);
      } catch (err) {
        if (!cancelled) console.error('Error fetching asset detail:', err);
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };

    fetchDetailData();
    return () => { cancelled = true; };
  }, [selectedAssetForDetail?.symbol]);

  // ── Filter + Sort ────────────────────────────────────────────────
  const [categoryFilter, setCategoryFilter] = useState<'All' | AssetCategory>('All');
  const [sortKey, setSortKey] = useState<SortKey>('value');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // ── Chart ────────────────────────────────────────────────────────
  const [timeframe, setTimeframe] = useState<'1D' | '1W' | '1M' | 'ALL'>('ALL');
  const [chartMode, setChartMode] = useState<'value' | 'pl'>('value');
  const [hoveredPoint, setHoveredPoint] = useState<{ x: number; y: number; val: number; label: string; index: number } | null>(null);

  // ── Sort helpers ─────────────────────────────────────────────────
  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const filtered = metrics.holdings.filter(h => categoryFilter === 'All' ? true : h.category === categoryFilter);

  const sortedHoldings = [...filtered].sort((a, b) => {
    const mul = sortDir === 'asc' ? 1 : -1;
    switch (sortKey) {
      case 'symbol':     return mul * a.symbol.localeCompare(b.symbol);
      case 'allocation': return mul * (a.allocationPercent - b.allocationPercent);
      case 'value':      return mul * (a.value - b.value);
      case 'pl':         return mul * (a.unrealizedPL - b.unrealizedPL);
      case 'plPct':      return mul * (a.unrealizedPLPercent - b.unrealizedPLPercent);
      case 'risk':       return mul * (a.riskScore - b.riskScore);
      default:           return 0;
    }
  });

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return <ChevronsUpDown className="w-3 h-3 ml-1 opacity-30 inline" />;
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 ml-1 text-[#8C9A86] inline" />
      : <ChevronDown className="w-3 h-3 ml-1 text-[#8C9A86] inline" />;
  };

  // ── Edit computations ────────────────────────────────────────────
  const editNewTotal = editingHolding
    ? editMode === 'increase'
      ? editingHolding.shares + editQty
      : Math.max(0, editingHolding.shares - editQty)
    : 0;

  const editNewAvg = editingHolding && editMode === 'increase' && editQty > 0 && editNewTotal > 0
    ? (editingHolding.shares * editingHolding.avgBuyPrice + editQty * editPrice) / editNewTotal
    : editingHolding?.avgBuyPrice ?? 0;

  const handleEditSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!editingHolding) return;
    // deltaQuantity/deltaPrice, bu düzenlemeyi GERÇEK bir işlem (top-up=BUY, azaltma=SELL)
    // olarak işlem geçmişine ekletmek için — editPrice, artırmada "bu ek payları hangi
    // fiyattan aldın", azaltmada "bu payları hangi fiyattan sattın" anlamına gelir.
    const deltaQuantity = editMode === 'increase' ? editQty : -editQty;
    onEditHolding(editingHolding.id, {
      symbol: editingHolding.symbol, name: editingHolding.name, category: editingHolding.category,
      sector: editingHolding.sector, shares: editingHolding.shares, avgBuyPrice: editingHolding.avgBuyPrice,
      currentPrice: editingHolding.currentPrice, riskScore: editingHolding.riskScore,
      buyDate: editingHolding.buyDate,
    }, editNewTotal, editNewAvg, deltaQuantity, editPrice);
    setEditingHolding(null);
  };

  const openEdit = (h: EnrichedHolding) => {
    // h.currentPrice ham kayan-nokta değeri olabilir (örn. 14.377510000000002) — input'a
    // doğrudan konursa kullanıcıya çirkin/okunaksız bir ondalık gösteriyordu.
    setEditingHolding(h); setEditMode('increase'); setEditQty(0); setEditPrice(Number(h.currentPrice.toFixed(4)));
  };

  // ── Add modal helpers ────────────────────────────────────────────
  const handleSelectMarketAsset = (symbol: string) => {
    const asset = MARKET_ASSETS.find(a => a.symbol === symbol);
    if (asset) {
      setNewSymbol(asset.symbol); setNewName(asset.name); setNewCategory(asset.category);
      // MARKET_ASSETS fiyatları zaten USD (bu preset'lerin native para birimi) — çevrim yapılmaz.
      setNewPrice(asset.price);
      if (asset.category === 'Crypto') { setNewSector('Cryptocurrency'); setNewRisk(9.0); }
      else if (asset.category === 'FixedIncome') { setNewSector('Government'); setNewRisk(1.5); }
      else { setNewSector('Technology'); setNewRisk(5.5); }
    }
  };

  const handleSubmitAdd = (e: FormEvent) => {
    e.preventDefault();
    if (!newSymbol || !newName || newShares <= 0 || newPrice <= 0 || !newBuyDate) return;
    onAddHolding({ symbol: newSymbol.toUpperCase(), name: newName, category: newCategory, sector: newSector, shares: Number(newShares), avgBuyPrice: Number(newPrice), currentPrice: Number(newPrice), riskScore: Number(newRisk), buyDate: newBuyDate });
    setNewSymbol(''); setNewName(''); setNewShares(10); setNewPrice(150); setNewBuyDate(new Date().toISOString().split('T')[0]); setShowAddModal(false);
  };

  // ── Performance chart data ────────────────────────────────────────
  const getPerformancePoints = () => {
    if (!performanceHistory || performanceHistory.length === 0) return [];
    const sliceLen = timeframe === 'ALL' ? performanceHistory.length : timeframe === '1M' ? 30 : timeframe === '1W' ? 7 : 5;
    const sliced = performanceHistory.slice(-sliceLen);
    if (!sliced.length) return [];
    // Backend now returns values in baseCurrency; anchor last point to current total
    const lastVal = sliced[sliced.length - 1].value || 1;
    const factor = metrics.totalValue > 0 && lastVal > 0 ? metrics.totalValue / lastVal : 1;

    return sliced.map(pt => {
      const d = new Date(pt.date);
      const label = (timeframe === '1D' || timeframe === '1W')
        ? d.toLocaleDateString('tr-TR', { weekday: 'short' })
        : d.toLocaleDateString('tr-TR', { year: performanceDays >= 365 ? 'numeric' : undefined, month: 'short', day: 'numeric' });
      const scaledValue = pt.value * factor;
      const scaledInvested = pt.invested || 0; // Maliyet ölçeklenmez — sadece değer ölçeklenir
      const val = chartMode === 'value' ? scaledValue : scaledValue - scaledInvested;
      return { label, val };
    });
  };

  const perfPoints = getPerformancePoints();
  const rawMin = perfPoints.length > 0 ? Math.min(...perfPoints.map(p => p.val)) : 0;
  const rawMax = perfPoints.length > 0 ? Math.max(...perfPoints.map(p => p.val)) : 1;
  const pad = (rawMax - rawMin) * 0.08 || Math.abs(rawMax) * 0.05 || 1;
  const minVal = chartMode === 'pl' ? rawMin - pad : rawMin * 0.99;
  const maxVal = chartMode === 'pl' ? rawMax + pad : rawMax * 1.01;
  const valRange = maxVal - minVal || 1;

  const getCatColor = (cat: string) => {
    const colors: Record<string, string> = {
      Equity: '#8C9A86',
      Crypto: '#B5836F',
      FixedIncome: '#D1CABF',
      Cash: '#9E958C',
      BIST_STOCK: '#E07A5F',
      TEFAS_FUND: '#D4A373',
      US_STOCK: '#1D3557',
      US_ETF: '#457B9D',
      CRYPTO: '#B5836F',
      COMMODITY: '#E9C46A',
      CASH: '#9E958C',
      OTHER: '#7F8C8D'
    };
    return colors[cat] || '#7F8C8D';
  };
  const getCatBg = (cat: AssetCategory) => ({ Equity: 'bg-[#8C9A86]/15 text-[#8C9A86]', Crypto: 'bg-[#B5836F]/15 text-[#B5836F]', FixedIncome: 'bg-[#D1CABF]/30 text-[#4A443F]', Cash: 'bg-[#9E958C]/20 text-[#4A443F]' }[cat]);
  // HHI (Herfindahl-Hirschman Index) tabanlı çeşitlendirme ve verimlilik skoru hesabı
  const hhiIndex = metrics.detailedAllocations.reduce(
    (sum, item) => sum + Math.pow(item.percent / 100, 2),
    0
  );
  const allocationEfficiencyScore = metrics.detailedAllocations.length > 0
    ? parseFloat((100 - hhiIndex * 60).toFixed(1))
    : 0;

  return (
    <div className="space-y-6">

      {/* HERO */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm relative overflow-hidden group">
          <div className="relative z-10">
            <div className="flex justify-between items-start flex-wrap gap-4">
              <div>
                <h2 className="font-serif text-[12px] font-bold text-[#9E958C] uppercase tracking-widest mb-1.5">{t.totalPortfolioValue}</h2>
                <div className="flex items-baseline gap-4 flex-wrap">
                  <span className="font-serif text-4xl sm:text-5xl font-bold tracking-tight text-[#2D2926]">{formatCurrency(metrics.totalValue, settings.baseCurrency)}</span>
                  <div className="flex items-center text-[#7A8874] font-mono text-xs font-bold bg-[#7A8874]/10 px-2.5 py-1 rounded">
                    <TrendingUp className="w-3.5 h-3.5 mr-1 shrink-0" />+{metrics.unrealizedPLPercent.toFixed(2)}%
                  </div>
                </div>
                <div className="text-xs text-[#6B645E] mt-1.5 font-semibold">
                  {t.totalProfitLoss}:{' '}
                  <span className={metrics.unrealizedPL >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}>
                    {metrics.unrealizedPL >= 0 ? '+' : ''}{formatCurrency(metrics.unrealizedPL, settings.baseCurrency)}
                  </span>
                </div>
                {liabilities.length > 0 && (() => {
                  const totalLiab = liabilities.reduce(
                    (sum, l) => sum + convertCurrency(l.amount, l.currency, settings.baseCurrency, exchangeRates), 0
                  );
                  const netWorth = metrics.totalValue - totalLiab;
                  return (
                    <div className="text-xs text-[#6B645E] mt-1 font-semibold" title={t.netWorthDesc}>
                      {t.netWorth}:{' '}
                      <span className="text-[#2D2926] font-bold">{formatCurrency(netWorth, settings.baseCurrency)}</span>
                      <span className="text-[#9E958C] font-medium"> ({t.totalLiabilities.toLowerCase()}: -{formatCurrency(totalLiab, settings.baseCurrency)})</span>
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
          <div className="absolute -right-20 -top-20 w-64 h-64 bg-[#8C9A86]/5 blur-[100px] rounded-full" />
        </div>

        <div className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col justify-center">
          <h3 className="font-serif text-[12px] font-bold text-[#9E958C] uppercase tracking-widest mb-4">{t.allocationStatus}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-xs text-[#6B645E] font-semibold">{t.availableLiquidity}</span>
              <span className="font-mono text-sm font-bold text-[#2D2926]">{formatCurrency(metrics.cashAmount, settings.baseCurrency)}</span>
            </div>
            {(() => {
              const inv = metrics.totalValue > 0 ? ((metrics.totalValue - metrics.cashAmount) / metrics.totalValue) * 100 : 0;
              const csh = 100 - inv;
              return (
                <>
                  <div className="w-full bg-[#F1EFE9] h-1.5 rounded-full overflow-hidden flex">
                    <div className="bg-[#8C9A86] h-full" style={{ width: `${inv}%` }} />
                    <div className="bg-[#9E958C] h-full" style={{ width: `${csh}%` }} />
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-[#6B645E] uppercase font-bold tracking-wider">
                    <span>{inv.toFixed(0)}% {t.invested}</span><span>{csh.toFixed(0)}% {t.cash}</span>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      </section>

      {/* METRICS */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          {
            label: t.netAlpha,
            val: performanceMetrics?.netAlpha != null
              ? `${performanceMetrics.netAlpha >= 0 ? '+' : ''}${performanceMetrics.netAlpha.toFixed(2)}%`
              : performanceMetrics?.twrr != null
              ? `${performanceMetrics.twrr >= 0 ? '+' : ''}${performanceMetrics.twrr.toFixed(2)}%`
              : '—',
            sub: t.vsBenchmark(settings.benchmark),
            icon: <Bolt className="w-4 h-4 text-[#8C9A86]" />,
            border: 'border-l-[#8C9A86]'
          },
          {
            label: t.sharpeRatio,
            val: (() => {
              if (!performanceMetrics || performanceMetrics.volatility <= 0) return '—';
              const RFR: Record<string, number> = { TRY: 42.5, USD: 4.5, EUR: 3.0, GBP: 4.75 };
              const annualRfr = RFR[settings.baseCurrency] ?? 0;
              const days = performanceDays ?? 90;
              const annualReturn = ((1 + performanceMetrics.twrr / 100) ** (365 / days) - 1) * 100;
              return ((annualReturn - annualRfr) / performanceMetrics.volatility).toFixed(2);
            })(),
            sub: t.riskAdjustedReturn,
            icon: <TrendingUp className="w-4 h-4 text-[#7A8874]" />,
            border: 'border-l-[#7A8874]'
          },
          {
            label: t.var,
            val: performanceMetrics
              ? `${performanceMetrics.max_drawdown.toFixed(1)}%`
              : '—',
            sub: t.confidenceInterval,
            icon: <AlertCircle className="w-4 h-4 text-[#B5836F]" />,
            border: 'border-l-[#B5836F]'
          },
        ].map(m => (
          <div key={m.label} className={`bg-white border-l-4 ${m.border} border-y border-r border-[#E8E2D9] p-5 rounded-xl shadow-sm`}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-serif text-[11px] font-bold text-[#9E958C] uppercase tracking-wider">{m.label}</span>
              {m.icon}
            </div>
            <div className="text-2xl font-bold font-serif text-[#2D2926] tracking-tight">{m.val}</div>
            <div className="text-[10px] text-[#6B645E] mt-1 font-semibold">{m.sub}</div>
          </div>
        ))}
      </section>

      {/* CHARTS */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Performance chart */}
        <div className="lg:col-span-2 bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col h-[400px]">
          <div className="flex justify-between items-center mb-4 flex-wrap gap-3">
            <div>
              <h3 className="font-serif text-lg font-bold text-[#2D2926]">{t.portfolioPerformance}</h3>
              <p className="text-xs text-[#6B645E] font-semibold">{t.twrrDesc}</p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {onPerformanceDaysChange && (
                <div className="flex bg-[#F1EFE9] rounded-lg p-1 border border-[#E8E2D9]">
                  {([90, 180, 365, 730] as const).map(d => (
                    <button key={d} onClick={() => {
                      onPerformanceDaysChange(d);
                      setTimeframe('ALL');
                    }}
                      className={`px-3 py-1 text-[10px] rounded font-bold transition-all ${performanceDays === d ? 'bg-[#8C9A86] text-white shadow-sm' : 'text-[#6B645E] hover:text-[#2D2926]'}`}>
                      {d === 90 ? '3M' : d === 180 ? '6M' : d === 365 ? '1Y' : '2Y'}
                    </button>
                  ))}
                </div>
              )}
              {/* Chart mode toggle */}
              <div className="flex bg-[#F1EFE9] rounded-lg p-1 border border-[#E8E2D9]">
                <button onClick={() => setChartMode('value')}
                  className={`px-3 py-1 text-[10px] rounded font-bold transition-all ${chartMode === 'value' ? 'bg-[#8C9A86] text-white shadow-sm' : 'text-[#6B645E] hover:text-[#2D2926]'}`}>
                  {t.chartModeValue}
                </button>
                <button onClick={() => setChartMode('pl')}
                  className={`px-3 py-1 text-[10px] rounded font-bold transition-all ${chartMode === 'pl' ? (metrics.unrealizedPL >= 0 ? 'bg-[#7A8874] text-white shadow-sm' : 'bg-[#B5836F] text-white shadow-sm') : 'text-[#6B645E] hover:text-[#2D2926]'}`}>
                  {t.chartModePL}
                </button>
              </div>
            </div>
          </div>
          <div className="flex-1 w-full relative" style={{ minHeight: 0 }}>
            {perfPoints.length > 1 ? (() => {
              const W = 560; const H = 200;
              const PAD_L = 0; const PAD_R = 36; const PAD_T = 10; const PAD_B = 24;
              const chartW = W - PAD_L - PAD_R;
              const chartH = H - PAD_T - PAD_B;
              const stepX = chartW / (perfPoints.length - 1);
              const coords = perfPoints.map((p, i) => ({
                x: PAD_L + i * stepX,
                y: PAD_T + chartH - ((p.val - minVal) / valRange) * chartH,
                val: p.val,
                label: p.label,
                index: i,
              }));

              // Smooth cubic bezier path
              const smoothPath = coords.reduce((acc, c, i) => {
                if (i === 0) return `M${c.x},${c.y}`;
                const prev = coords[i - 1];
                const cpx = (prev.x + c.x) / 2;
                return `${acc} C${cpx},${prev.y} ${cpx},${c.y} ${c.x},${c.y}`;
              }, '');

              const lastC = coords[coords.length - 1];
              const firstC = coords[0];
              const lastVal = lastC.val;
              const firstVal = firstC.val;
              const changePct = firstVal !== 0 ? ((lastVal - firstVal) / Math.abs(firstVal)) * 100 : 0;
              const lineColor = chartMode === 'pl' ? (lastVal >= 0 ? '#7A8874' : '#B5836F') : (changePct >= 0 ? '#7A8874' : '#B5836F');
              const zeroY = chartMode === 'pl' ? PAD_T + chartH - ((0 - minVal) / valRange) * chartH : null;

              // Y-axis grid values (4 levels)
              const yLevels = [0, 1, 2, 3].map(i => minVal + (valRange * i) / 3);

              const hovered = hoveredPoint;
              const hovIdx = hovered ? hovered.index : -1;

              return (
                <div className="w-full h-full flex flex-col">
                  {/* Change badge */}
                  <div className="flex items-center gap-3 mb-3 px-1">
                    <span className={`inline-flex items-center gap-1 text-[11px] font-mono font-bold px-2 py-0.5 rounded ${changePct >= 0 ? 'bg-[#7A8874]/10 text-[#7A8874]' : 'bg-[#B5836F]/10 text-[#B5836F]'}`}>
                      {changePct >= 0 ? '▲' : '▼'} {Math.abs(changePct).toFixed(2)}%
                    </span>
                    <span className="text-[10px] text-[#9E958C] font-semibold">{perfPoints[0]?.label} → {perfPoints[perfPoints.length - 1]?.label}</span>
                    {hovered && (
                      <span className="ml-auto text-[10px] font-semibold text-[#6B645E]">
                        <span className="text-[#9E958C] mr-1">{hovered.label}</span>
                        <span className={`font-mono font-bold ${chartMode === 'pl' ? (hovered.val >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]') : 'text-[#2D2926]'}`}>
                          {chartMode === 'pl' && hovered.val >= 0 ? '+' : ''}{formatCurrency(hovered.val, settings.baseCurrency)}
                        </span>
                      </span>
                    )}
                  </div>

                  {/* SVG chart */}
                  <div className="flex-1 relative">
                    <svg
                      className="w-full h-full"
                      viewBox={`0 0 ${W} ${H}`}
                      preserveAspectRatio="none"
                      onMouseMove={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const x = e.clientX - rect.left;
                        const pct = x / rect.width;
                        const idx = Math.max(0, Math.min(coords.length - 1, Math.round(pct * (coords.length - 1))));
                        setHoveredPoint(coords[idx]);
                      }}
                      onMouseLeave={() => setHoveredPoint(null)}
                    >
                      <defs>
                        <linearGradient id={`grad-${chartMode}`} x1="0%" x2="0%" y1="0%" y2="100%">
                          <stop offset="0%" stopColor={lineColor} stopOpacity="0.22" />
                          <stop offset="60%" stopColor={lineColor} stopOpacity="0.06" />
                          <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
                        </linearGradient>
                        <clipPath id="chart-clip">
                          <rect x={PAD_L} y={PAD_T} width={chartW} height={chartH} />
                        </clipPath>
                      </defs>

                      {/* Y-axis grid lines + labels */}
                      {yLevels.map((v, i) => {
                        const gy = PAD_T + chartH - ((v - minVal) / valRange) * chartH;
                        const label = chartMode === 'pl'
                          ? `${v >= 0 ? '+' : ''}${(v / 1000).toFixed(0)}K`
                          : `${(v / 1000).toFixed(0)}K`;
                        return (
                          <g key={i}>
                            <line x1={PAD_L} y1={gy} x2={W - PAD_R} y2={gy}
                              stroke={i === 0 ? '#D1CABF' : '#E8E2D9'} strokeWidth="0.8"
                              strokeDasharray={i === 0 ? '0' : '3,4'} />
                            <text x={W - PAD_R + 4} y={gy + 3.5} fontSize="7.5" fill="#9E958C"
                              fontFamily="monospace" textAnchor="start">{label}</text>
                          </g>
                        );
                      })}

                      {/* Zero line (P/L mode) */}
                      {zeroY !== null && zeroY >= PAD_T && zeroY <= PAD_T + chartH && (
                        <line x1={PAD_L} y1={zeroY} x2={W - PAD_R} y2={zeroY}
                          stroke="#9E958C" strokeWidth="1" strokeDasharray="4,3" opacity="0.7" />
                      )}

                      {/* Area fill */}
                      <path
                        d={`${smoothPath} L${lastC.x},${PAD_T + chartH} L${firstC.x},${PAD_T + chartH} Z`}
                        fill={`url(#grad-${chartMode})`} clipPath="url(#chart-clip)" />

                      {/* Main line */}
                      <path d={smoothPath} fill="none" stroke={lineColor} strokeWidth="2"
                        strokeLinecap="round" strokeLinejoin="round" clipPath="url(#chart-clip)" />

                      {/* Crosshair + hover point */}
                      {hovIdx >= 0 && (() => {
                        const hc = coords[hovIdx];
                        return (
                          <g>
                            <line x1={hc.x} y1={PAD_T} x2={hc.x} y2={PAD_T + chartH}
                              stroke={lineColor} strokeWidth="0.8" strokeDasharray="3,3" opacity="0.6" />
                            <circle cx={hc.x} cy={hc.y} r="5" fill={lineColor} opacity="0.2" />
                            <circle cx={hc.x} cy={hc.y} r="3.5" fill={lineColor} />
                            <circle cx={hc.x} cy={hc.y} r="1.5" fill="white" />
                          </g>
                        );
                      })()}

                      {/* Last point pulse dot */}
                      {hovIdx < 0 && (
                        <g>
                          <circle cx={lastC.x} cy={lastC.y} r="6" fill={lineColor} opacity="0.15" />
                          <circle cx={lastC.x} cy={lastC.y} r="3" fill={lineColor} />
                          <circle cx={lastC.x} cy={lastC.y} r="1.2" fill="white" />
                        </g>
                      )}

                      {/* X-axis labels — evenly spaced subset */}
                      {coords.filter((_, i) => {
                        const step = Math.max(1, Math.floor(coords.length / 5));
                        return i % step === 0 || i === coords.length - 1;
                      }).map((c, i) => (
                        <text key={i} x={c.x} y={H - 4} fontSize="8" fill="#9E958C"
                          fontFamily="monospace" textAnchor="middle">{c.label}</text>
                      ))}

                    </svg>
                  </div>
                </div>
              );
            })() : (
              <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-[#9E958C]">
                <div className="w-8 h-8 rounded-full border-2 border-[#E8E2D9] flex items-center justify-center text-lg">—</div>
                <span className="text-xs font-semibold">{t.noDataAccumulated}</span>
              </div>
            )}
          </div>
        </div>

        {/* Donut */}
        <div className="bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col h-[400px]">
          <h3 className="font-serif text-base font-bold text-[#2D2926] mb-1">{t.riskAllocation}</h3>
          <p className="text-xs text-[#6B645E] mb-4 font-semibold">{t.riskAllocDesc}</p>
          <div className="flex-1 flex flex-row items-center justify-between gap-4 mt-2">
            <div className="relative w-36 h-36 shrink-0">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="16" fill="none" stroke="#F1EFE9" strokeWidth="3" />
                {(() => { let acc = 0; return metrics.detailedAllocations.map(a => { if (a.value <= 0) return null; const off = acc; acc += a.percent; return <circle key={a.category} cx="18" cy="18" r="16" fill="none" stroke={getCatColor(a.category)} strokeWidth="3.2" strokeDasharray={`${a.percent} ${100 - a.percent}`} strokeDashoffset={-off} strokeLinecap="round" className="transition-all duration-300" />; }); })()}
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-xl font-bold font-serif tracking-tight text-[#2D2926]">{allocationEfficiencyScore}</span>
                <span className="text-[8px] uppercase tracking-wider font-bold text-[#9E958C]">{t.efficScore}</span>
              </div>
            </div>
            <div className="flex-1 space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {metrics.detailedAllocations.map(a => (
                <div key={a.category} className="flex items-center justify-between py-0.5 animate-fade-in">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: getCatColor(a.category) }} />
                    <span className="text-[11px] font-semibold text-[#6B645E] truncate">
                      {(() => {
                        switch (a.category) {
                          case 'BIST_STOCK': return t.detBistStock;
                          case 'TEFAS_FUND': return t.detTefasFund;
                          case 'US_STOCK': return t.detUsStock;
                          case 'US_ETF': return t.detUsEtf;
                          case 'CRYPTO': return t.detCrypto;
                          case 'COMMODITY': return t.detCommodity;
                          case 'CASH': return t.detCash;
                          default: return t.detOther;
                        }
                      })()}
                    </span>
                  </div>
                  <span className="text-[11px] font-mono font-bold text-[#2D2926] ml-2 shrink-0">{a.percent.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* HOLDINGS TABLE */}
      <section className="bg-white border border-[#E8E2D9] rounded-2xl shadow-sm overflow-hidden">
        <div className="p-6 border-b border-[#E8E2D9] flex justify-between items-center flex-wrap gap-4 select-none">
          <div>
            <h3 className="font-serif text-lg font-bold text-[#2D2926]">{t.currentHoldings}</h3>
            <p className="text-xs text-[#6B645E] font-semibold">{t.holdingsDesc}</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex bg-[#F1EFE9] border border-[#E8E2D9] p-1 rounded-lg gap-1">
              {(['All', 'Equity', 'Crypto', 'FixedIncome', 'Cash'] as const).map(cat => (
                <button key={cat} onClick={() => setCategoryFilter(cat)}
                  className={`px-3 py-1 text-[10px] font-bold rounded cursor-pointer transition-all ${categoryFilter === cat ? 'bg-[#8C9A86] text-white shadow-sm' : 'text-[#6B645E] hover:text-[#2D2926]'}`}>
                  {cat === 'All' ? t.all : cat === 'FixedIncome' ? t.bonds : cat === 'Equity' ? t.equity : cat === 'Crypto' ? t.crypto : t.cash}
                </button>
              ))}
            </div>
            <button onClick={() => setShowAddModal(true)}
              className="flex items-center gap-1.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white px-5 py-2.5 rounded-full text-[11px] font-bold uppercase tracking-widest transition-all shadow-sm">
              <Plus className="w-3.5 h-3.5" />{t.addTransaction}
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse select-none">
            <thead>
              <tr className="bg-[#F1EFE9] border-b border-[#E8E2D9] text-[10px] font-bold uppercase tracking-wider text-[#6B645E]">
                <th className="px-6 py-4 cursor-pointer hover:text-[#2D2926]" onClick={() => handleSort('symbol')}>
                  {t.assetName}<SortIcon k="symbol" />
                </th>
                <th className="px-6 py-4 text-right cursor-pointer hover:text-[#2D2926]" onClick={() => handleSort('allocation')}>
                  {t.allocation}<SortIcon k="allocation" />
                </th>
                <th className="px-6 py-4 text-right">{t.sharesQty}</th>
                <th className="px-6 py-4 text-right cursor-pointer hover:text-[#2D2926]" onClick={() => handleSort('value')}>
                  {t.currentValue}<SortIcon k="value" />
                </th>
                <th className="px-6 py-4 text-right cursor-pointer hover:text-[#2D2926]" onClick={() => handleSort('pl')}>
                  {t.unrealizedPL}<SortIcon k="pl" />
                </th>
                <th className="px-6 py-4 text-right cursor-pointer hover:text-[#2D2926]" onClick={() => handleSort('risk')}>
                  {t.riskScore}<SortIcon k="risk" />
                </th>
                <th className="px-6 py-4 text-center">{t.action}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E2D9]/40">
              {sortedHoldings.length > 0 ? sortedHoldings.map(h => (
                <tr key={h.id} className="hover:bg-[#F1EFE9]/30 transition-colors">
                  <td className="px-6 py-4 cursor-pointer hover:bg-[#8C9A86]/5 group/item rounded-l-lg transition-all"
                      onClick={() => setSelectedAssetForDetail(h)}>
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded flex items-center justify-center font-mono text-xs font-bold ${getCatBg(h.category)}`}>
                        {h.symbol.substring(0, 2)}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-[#2D2926] group-hover/item:text-[#8C9A86] transition-colors">{h.name}</div>
                        <div className="text-[10px] text-[#6B645E] font-semibold uppercase tracking-wider mt-0.5">{h.symbol} • {h.sector}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-[#2D2926] font-semibold">{h.allocationPercent.toFixed(1)}%</td>
                  <td className="px-6 py-4 text-right">
                    <div className="text-sm text-[#2D2926] font-mono font-semibold">{h.shares.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}</div>
                    <div className="text-[10px] text-[#6B645E] font-mono font-medium mt-0.5">{t.avgLabel} {formatCurrency(h.avgBuyPrice, settings.baseCurrency)}</div>
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-[#2D2926] font-bold">{formatCurrency(h.value, settings.baseCurrency)}</td>
                  <td className="px-6 py-4 text-right">
                    <span className={`font-mono text-sm font-bold flex items-center justify-end gap-0.5 ${h.unrealizedPL >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                      {h.unrealizedPL >= 0 ? '+' : ''}{formatCurrency(h.unrealizedPL, settings.baseCurrency)}
                    </span>
                    <span className={`text-[10px] font-mono font-bold block mt-0.5 ${h.unrealizedPL >= 0 ? 'text-[#7A8874]/85' : 'text-[#B5836F]/85'}`}>
                      {h.unrealizedPL >= 0 ? '+' : ''}{h.unrealizedPLPercent.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end items-center gap-2.5">
                      <div className="w-16 bg-[#F1EFE9] h-1 rounded-full overflow-hidden shrink-0 hidden sm:block">
                        <div className="h-full rounded-full" style={{ width: `${h.riskScore * 10}%`, backgroundColor: h.riskScore >= 7 ? '#B5836F' : h.riskScore >= 4 ? '#D1CABF' : '#7A8874' }} />
                      </div>
                      <span className={`text-xs font-mono font-bold ${h.riskScore >= 7 ? 'text-[#B5836F]' : h.riskScore >= 4 ? 'text-[#9E958C]' : 'text-[#7A8874]'}`}>{h.riskScore.toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-center">
                    {/* Sarmalayıcı div koşulsuz render edilir (içindeki butonlar koşullu) — aksi halde
                        nakit satırlarında hücre tamamen boş kalıp o satırın diğerlerinden daha kısa
                        görünmesine (satırların hizasız/kaymış gibi görünmesine) yol açıyordu. Ayrıca
                        eskiden sadece USD nakit hariç tutuluyordu, TRY/EUR/GBP nakit için buton
                        yanlışlıkla gösteriliyordu — artık tüm nakit pozisyonları tutarlı davranıyor. */}
                    <div className="flex items-center justify-center gap-1 h-7">
                      {h.category !== 'Cash' && (
                        <>
                          <button onClick={() => openEdit(h)} title={t.editPosition}
                            className="text-[#9E958C]/60 hover:text-[#8C9A86] p-1.5 rounded hover:bg-[#8C9A86]/10 transition-all">
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button onClick={() => onDeleteHolding(h.id)} title={t.deletePosition}
                            className="text-[#9E958C]/60 hover:text-[#B5836F] p-1.5 rounded hover:bg-[#B5836F]/10 transition-all">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={7} className="text-center py-12 text-sm text-[#6B645E]/70 font-semibold">{t.noPositions}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── EDIT MODAL ───────────────────────────────────────────── */}
      <AnimatePresence>
        {editingHolding && (
          <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
              <div className="px-6 py-4 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F1EFE9]">
                <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
                  <Pencil className="w-4 h-4 text-[#8C9A86]" />
                  {t.editPosition} — {editingHolding.symbol}
                </h3>
                <button onClick={() => setEditingHolding(null)} aria-label={t.detailClose} className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors"><X className="w-4 h-4" /></button>
              </div>

              <form onSubmit={handleEditSubmit} className="p-6 space-y-5">
                {/* Current position */}
                <div className="bg-[#F1EFE9] border border-[#E8E2D9] rounded-xl p-4">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-3">{t.currentPositionLabel}</div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.sharesQty}</div>
                      <div className="text-sm font-mono font-bold text-[#2D2926]">{editingHolding.shares.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.buyPriceAvg}</div>
                      <div className="text-sm font-mono font-bold text-[#2D2926]">{formatCurrency(editingHolding.avgBuyPrice, settings.baseCurrency)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.currentValue}</div>
                      <div className="text-sm font-mono font-bold text-[#2D2926]">{formatCurrency(editingHolding.value, settings.baseCurrency)}</div>
                    </div>
                  </div>
                </div>

                {/* Mode toggle */}
                <div className="flex gap-2">
                  {(['increase', 'decrease'] as const).map(m => (
                    <button key={m} type="button" onClick={() => { setEditMode(m); setEditQty(0); }}
                      className={`flex-1 py-2 rounded-lg border text-xs font-bold uppercase tracking-widest transition-all ${editMode === m ? (m === 'increase' ? 'bg-[#8C9A86] text-white border-[#8C9A86]' : 'bg-[#B5836F] text-white border-[#B5836F]') : 'bg-[#F1EFE9] text-[#6B645E] border-[#E8E2D9] hover:bg-[#E8E2D9]'}`}>
                      {m === 'increase' ? `+ ${t.addMore}` : `− ${t.reducePosition}`}
                    </button>
                  ))}
                </div>

                {/* Qty */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5">
                    {editMode === 'increase' ? t.additionalQtyLabel : t.reduceQtyLabel}
                  </label>
                  <input type="number" step="any" min="0.0001"
                    max={editMode === 'decrease' ? editingHolding.shares : undefined}
                    required value={editQty || ''}
                    onChange={e => setEditQty(Number(e.target.value))}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                </div>

                {/* Price (increase only) */}
                {editMode === 'increase' && (
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5">{t.transactionPriceLabel}</label>
                    <input type="number" step="any" min="0.0001" required value={editPrice || ''}
                      onChange={e => setEditPrice(Number(e.target.value))}
                      className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                  </div>
                )}

                {/* Live preview */}
                {editQty > 0 && (
                  <div className="bg-[#F1EFE9] border border-[#E8E2D9] rounded-xl p-4 grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.newTotalQtyLabel}</div>
                      <div className={`text-sm font-mono font-bold ${editMode === 'increase' ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                        {editNewTotal.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}
                      </div>
                    </div>
                    {editMode === 'increase' && editQty > 0 && (
                      <div>
                        <div className="text-[10px] text-[#9E958C] font-semibold">{t.newAvgPriceLabel}</div>
                        <div className="text-sm font-mono font-bold text-[#8C9A86]">{formatCurrency(editNewAvg, settings.baseCurrency)}</div>
                      </div>
                    )}
                  </div>
                )}

                {/* Sell all shortcut */}
                {editMode === 'decrease' && (
                  <button type="button" onClick={() => setEditQty(editingHolding.shares)}
                    className="w-full py-1.5 text-[11px] font-bold text-[#B5836F] border border-[#B5836F]/30 rounded-lg hover:bg-[#B5836F]/5 transition-colors">
                    {t.sellAll}
                  </button>
                )}

                <div className="flex justify-end gap-3 pt-2 border-t border-[#E8E2D9]">
                  <button type="button" onClick={() => setEditingHolding(null)}
                    className="px-5 py-2 border border-[#E8E2D9] text-xs font-bold text-[#6B645E] rounded-full hover:bg-[#F1EFE9] transition-all">
                    {t.cancel}
                  </button>
                  <button type="submit" disabled={editQty <= 0}
                    className="px-6 py-2.5 bg-[#8C9A86] hover:bg-[#7A8874] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">
                    {t.confirmEdit}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── ADD MODAL ────────────────────────────────────────────── */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
              <div className="px-6 py-4 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F1EFE9]">
                <h3 className="text-xs font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
                  <Wallet2 className="w-4 h-4 text-[#8C9A86]" />{t.logNewAsset}
                </h3>
                <button onClick={() => setShowAddModal(false)} aria-label={t.detailClose} className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors"><X className="w-4 h-4" /></button>
              </div>
              <form onSubmit={handleSubmitAdd} className="p-6 space-y-4 overflow-y-auto custom-scrollbar">
                {/* 1. Category Selector */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.assetCategory}</label>
                  <select value={newCategory} onChange={e => setNewCategory(e.target.value as AssetCategory)}
                    className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold">
                    <option value="Equity">{t.equityOption}</option>
                    <option value="Crypto">{t.cryptoOption}</option>
                    <option value="FixedIncome">{t.fixedIncomeOption}</option>
                    <option value="Cash">{t.cashOption}</option>
                  </select>
                </div>

                {/* 2. Preset Lookup (Only for non-Cash) */}
                {newCategory !== 'Cash' && (
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-2 font-serif">{t.quickPreset}</label>
                    <div className="flex flex-wrap gap-1.5 bg-[#F1EFE9] p-2 rounded-lg border border-[#E8E2D9]">
                      {MARKET_ASSETS.filter(a => {
                        if (newCategory === 'Equity') return a.category === 'Equity';
                        if (newCategory === 'Crypto') return a.category === 'Crypto';
                        if (newCategory === 'FixedIncome') return a.category === 'FixedIncome';
                        return false;
                      }).map(asset => (
                        <button key={asset.symbol} type="button" onClick={() => handleSelectMarketAsset(asset.symbol)}
                          className={`px-2.5 py-1 rounded text-[10px] font-mono font-bold border transition-all ${newSymbol === asset.symbol ? 'bg-[#8C9A86]/20 border-[#8C9A86] text-[#7A8874]' : 'bg-white border-[#E8E2D9] text-[#6B645E] hover:text-[#2D2926]'}`}>
                          {asset.symbol}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* 3. Dynamic Inputs */}
                {newCategory === 'Cash' ? (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.cashCurrency}</label>
                      <select value={newSymbol} onChange={e => {
                        const cur = e.target.value;
                        setNewSymbol(cur);
                        setNewName(settings.language === 'tr' ? `${cur} Nakit` : `${cur} Cash`);
                      }}
                        className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-semibold">
                        <option value="TRY">TRY</option>
                        <option value="USD">USD</option>
                        <option value="EUR">EUR</option>
                        <option value="GBP">GBP</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.cashAmount}</label>
                      <input type="number" step="any" required min="0.0001" value={newShares} onChange={e => setNewShares(Number(e.target.value))}
                        className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.buyDateLabel}</label>
                      <input type="date" required max={new Date().toISOString().split('T')[0]} value={newBuyDate} onChange={e => setNewBuyDate(e.target.value)}
                        className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="relative">
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">
                          {newCategory === 'FixedIncome' ? t.bondSymbol : newCategory === 'Crypto' ? t.cryptoSymbol : t.tickerSymbol}
                        </label>
                        <input type="text" required value={newSymbol}
                          onChange={e => {
                            setNewSymbol(e.target.value.toUpperCase());
                            setShowSuggestions(true);
                          }}
                          onFocus={() => setShowSuggestions(true)}
                          onBlur={() => {
                            handleSymbolBlur();
                            setTimeout(() => setShowSuggestions(false), 200);
                          }}
                          placeholder={newCategory === 'FixedIncome' ? 'US10Y' : newCategory === 'Crypto' ? 'BTC' : 'AAPL'}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-medium" />
                        
                        {/* Suggestions Dropdown */}
                        {showSuggestions && (suggestions.length > 0 || loadingSuggestions) && (
                          <div className="absolute left-0 right-0 mt-1 bg-white border border-[#E8E2D9] rounded-lg shadow-lg z-[60] max-h-60 overflow-y-auto">
                            {loadingSuggestions ? (
                              <div className="p-3 text-xs text-[#9E958C] italic">{t.searching}</div>
                            ) : (
                              suggestions.map((item) => (
                                <button
                                  key={item.symbol}
                                  type="button"
                                  onClick={() => handleSelectSuggestion(item)}
                                  className="w-full text-left px-4 py-2 hover:bg-[#F1EFE9] border-b border-[#E8E2D9]/50 last:border-0 flex flex-col"
                                >
                                  <div className="flex justify-between items-center">
                                    <span className="font-mono font-bold text-xs text-[#2D2926]">{item.symbol}</span>
                                    <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded bg-[#E8E2D9] text-[#6B645E]">
                                      {item.asset_class}
                                    </span>
                                  </div>
                                  <span className="text-[11px] text-[#6B645E] truncate">{item.name}</span>
                                </button>
                              ))
                            )}
                          </div>
                        )}
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">
                          {newCategory === 'FixedIncome' ? t.bondName : newCategory === 'Crypto' ? t.cryptoName : t.assetName}
                        </label>
                        <input type="text" required value={newName} onChange={e => setNewName(e.target.value)}
                          placeholder={newCategory === 'FixedIncome' ? 'US 10-Year Bond' : newCategory === 'Crypto' ? 'Bitcoin' : 'Apple Inc'}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-medium" />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.sectorTag}</label>
                        <input type="text" required value={newSector} onChange={e => setNewSector(e.target.value)}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-medium" />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.riskScore110}</label>
                        <input type="number" step="0.1" required min="0" max="10" value={newRisk} onChange={e => setNewRisk(Number(e.target.value))}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.quantityShares}</label>
                        <input type="number" step="any" required min="0.0001" value={newShares} onChange={e => setNewShares(Number(e.target.value))}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.buyPriceAvg} ({nativeBuyCurrency})</label>
                        <input type="number" step="any" required min="0.01" value={newPrice} onChange={e => setNewPrice(Number(e.target.value))}
                          className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-1.5 font-serif">{t.buyDateLabel}</label>
                      <input type="date" required max={new Date().toISOString().split('T')[0]} value={newBuyDate} onChange={e => setNewBuyDate(e.target.value)}
                        className="w-full bg-white border border-[#E8E2D9] text-sm text-[#2D2926] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8C9A86] focus:border-[#8C9A86] font-mono font-medium" />
                    </div>
                  </>
                )}

                {/* 3.5 Mini chart & price info */}
                {newCategory !== 'Cash' && newSymbol && (
                  <div className="bg-[#F1EFE9]/50 border border-[#E8E2D9] rounded-xl p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider block">{t.lastPrice}</span>
                        <div className="text-lg font-mono font-bold text-[#2D2926]">
                          {formatCurrency(newPrice, nativeBuyCurrency)}
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider block">{t.riskScoreSector}</span>
                        <span className="text-xs font-semibold text-[#6B645E]">
                          {newSector} (Risk: {newRisk})
                        </span>
                      </div>
                    </div>

                    {/* Chart */}
                    {loadingModalHistory ? (
                      <div className="h-24 flex items-center justify-center text-xs text-[#6B645E] italic">{t.historyLoading}</div>
                    ) : modalHistory && modalHistory.length > 1 ? (
                      <div className="h-24 w-full relative pt-4 flex flex-col justify-between">
                        {(() => {
                          const prices = modalHistory.map(h => h.price);
                          const minP = Math.min(...prices);
                          const maxP = Math.max(...prices);
                          const rangeP = maxP - minP || 1;
                          
                          const w = 450;
                          const h = 50;
                          const stepX = w / (modalHistory.length - 1);
                          const points = modalHistory.map((pt, i) => {
                            const x = i * stepX;
                            const y = h - ((pt.price - minP) / rangeP) * h;
                            return `${x},${y}`;
                          }).join(' ');

                          const chartCurrency = newAssetClass === 'BIST Hissesi' || newAssetClass === 'TEFAS Fonu' ? 'TRY' : 'USD';

                          return (
                            <>
                              <div className="absolute top-0 left-0 text-[8px] font-mono font-bold text-[#8C9A86]">
                                En Yüksek: {formatCurrency(maxP, chartCurrency)}
                              </div>
                              <div className="absolute top-0 right-0 text-[8px] font-mono font-bold text-[#B5836F]">
                                En Düşük: {formatCurrency(minP, chartCurrency)}
                              </div>
                              <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-[50px] overflow-visible mt-2">
                                <polyline
                                  fill="none"
                                  stroke="#8C9A86"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  points={points}
                                />
                              </svg>
                              <div className="flex justify-between text-[8px] font-mono font-bold text-[#9E958C] uppercase tracking-wider mt-1">
                                <span>{new Date(modalHistory[0].date).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' })}</span>
                                <span>{new Date(modalHistory[modalHistory.length - 1].date).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' })}</span>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    ) : (
                      <div className="h-10 flex items-center justify-center text-[10px] text-[#6B645E]/50 italic">{t.noHistory30d}</div>
                    )}
                  </div>
                )}

                {/* 4. Cost/Outlay Preview */}
                <div className="p-3 bg-[#F1EFE9] rounded-lg border border-[#E8E2D9] text-xs text-[#6B645E]">
                  <div className="flex justify-between font-semibold">
                    <span>{t.estimatedOutlay}</span>
                    <span className="font-mono text-[#2D2926] font-bold">{formatCurrency(newShares * newPrice, nativeBuyCurrency)}</span>
                  </div>
                </div>

                {/* 5. Buttons */}
                <div className="flex justify-end gap-3 pt-4 border-t border-[#E8E2D9]">
                  <button type="button" onClick={() => setShowAddModal(false)}
                    className="px-5 py-2 border border-[#E8E2D9] text-xs font-bold text-[#6B645E] rounded-full hover:bg-[#F1EFE9] transition-all">{t.cancel}</button>
                  <button type="submit"
                    className="px-6 py-2.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white text-xs font-bold rounded-full uppercase tracking-widest transition-all shadow-sm">{t.confirmOrder}</button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── DETAIL MODAL ─────────────────────────────────────────── */}
      <AnimatePresence>
        {selectedAssetForDetail && (
          <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-50 flex items-center justify-center p-4">
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto">
              <div className="px-6 py-4 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F1EFE9]">
                <h3 className="text-sm font-bold text-[#2D2926] uppercase tracking-widest flex items-center gap-2 font-serif">
                  <TrendingUp className="w-4 h-4 text-[#8C9A86]" />
                  {selectedAssetForDetail.name} ({selectedAssetForDetail.symbol})
                </h3>
                <button onClick={() => setSelectedAssetForDetail(null)} aria-label={t.detailClose} className="text-[#6B645E] hover:text-[#2D2926] p-1.5 rounded-full hover:bg-[#E8E2D9] transition-colors"><X className="w-4 h-4" /></button>
              </div>

              <div className="p-6 space-y-6">
                {/* NAKİT POZİSYON GÖRÜNÜMÜ */}
                {selectedAssetForDetail.category === 'Cash' ? (
                  <div className="space-y-4">
                    <div className="bg-[#F1EFE9] border border-[#E8E2D9] rounded-xl p-5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-4">{t.detailCashTitle}</div>
                      <div className="grid grid-cols-2 gap-6">
                        <div className="text-center">
                          <div className="text-[10px] text-[#9E958C] font-semibold mb-1">{t.detailAmount}</div>
                          <div className="text-2xl font-mono font-bold text-[#2D2926]">
                            {selectedAssetForDetail.shares.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} {selectedAssetForDetail.symbol}
                          </div>
                        </div>
                        <div className="text-center">
                          <div className="text-[10px] text-[#9E958C] font-semibold mb-1">{t.detailPortfolioValue}</div>
                          <div className="text-2xl font-mono font-bold text-[#8C9A86]">
                            {formatCurrency(selectedAssetForDetail.value, settings.baseCurrency)}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="bg-white border border-[#E8E2D9] rounded-xl p-4 flex items-center gap-3">
                      <Wallet2 className="w-5 h-5 text-[#9E958C] shrink-0" />
                      <p className="text-xs text-[#6B645E] font-medium leading-relaxed">
                        {t.detailCashNote}
                      </p>
                    </div>
                  </div>
                ) : (
                <>
                {/* 1. KULLANICI POZİSYON DETAYLARI */}
                <div className="bg-[#F1EFE9] border border-[#E8E2D9] rounded-xl p-4">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-3">{t.detailPositionTitle}</div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.detailCurrentQty}</div>
                      <div className="text-base font-mono font-bold text-[#2D2926]">{selectedAssetForDetail.shares.toLocaleString('tr-TR', { maximumFractionDigits: 4 })}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.detailAvgCost}</div>
                      <div className="text-base font-mono font-bold text-[#2D2926]">{formatCurrency(selectedAssetForDetail.avgBuyPrice, settings.baseCurrency)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.detailCurrentValue}</div>
                      <div className="text-base font-mono font-bold text-[#2D2926]">{formatCurrency(selectedAssetForDetail.value, settings.baseCurrency)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-[#9E958C] font-semibold">{t.detailPL}</div>
                      <span className={`text-base font-mono font-bold block ${selectedAssetForDetail.unrealizedPL >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                        {selectedAssetForDetail.unrealizedPL >= 0 ? '+' : ''}{formatCurrency(selectedAssetForDetail.unrealizedPL, settings.baseCurrency)}
                      </span>
                      <span className={`text-[10px] font-mono font-semibold ${selectedAssetForDetail.unrealizedPL >= 0 ? 'text-[#7A8874]/80' : 'text-[#B5836F]/80'}`}>
                        {selectedAssetForDetail.unrealizedPL >= 0 ? '+' : ''}{selectedAssetForDetail.unrealizedPLPercent.toFixed(2)}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* 2. GEÇMİŞ FİYAT GRAFİĞİ */}
                <div>
                  <h4 className="font-serif text-xs font-bold text-[#9E958C] uppercase tracking-wider mb-3">{t.detailPriceHistoryTitle}</h4>
                  {loadingDetail ? (
                    <div className="h-40 flex items-center justify-center text-xs text-[#6B645E] font-medium">{t.detailChartLoading}</div>
                  ) : detailHistory && detailHistory.length > 1 ? (
                    <div className="h-44 w-full relative bg-[#F1EFE9]/40 border border-[#E8E2D9] rounded-xl p-4 pt-8 flex flex-col justify-between">
                      {(() => {
                        const prices = detailHistory.map(h => h.price);
                        const minP = Math.min(...prices);
                        const maxP = Math.max(...prices);
                        const rangeP = maxP - minP || 1;
                        
                        const w = 550;
                        const h = 100;
                        const stepX = w / (detailHistory.length - 1);
                        const points = detailHistory.map((pt, i) => {
                          const x = i * stepX;
                          const y = h - ((pt.price - minP) / rangeP) * h;
                          return `${x},${y}`;
                        }).join(' ');

                        return (
                          <>
                            <div className="absolute top-2.5 left-4 text-[10px] font-mono font-bold text-[#8C9A86]">
                              {t.detailHigh} {formatCurrency(maxP, settings.baseCurrency)}
                            </div>
                            <div className="absolute top-2.5 right-4 text-[10px] font-mono font-bold text-[#B5836F]">
                              {t.detailLow} {formatCurrency(minP, settings.baseCurrency)}
                            </div>
                            <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-[95px] overflow-visible">
                              <polyline
                                fill="none"
                                stroke="#8C9A86"
                                strokeWidth="2.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                points={points}
                              />
                            </svg>
                            <div className="flex justify-between text-[8px] font-mono font-bold text-[#9E958C] uppercase tracking-wider mt-1 px-1">
                              <span>{new Date(detailHistory[0].date).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' })}</span>
                              <span>{new Date(detailHistory[detailHistory.length - 1].date).toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' })}</span>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-xs text-[#6B645E]/70 font-semibold border border-dashed border-[#E8E2D9] rounded-xl">{t.detailNoChartData}</div>
                  )}
                </div>

                {/* 3. TEMEL ANALİZ VE AÇIKLAMA */}
                <div>
                  <h4 className="font-serif text-xs font-bold text-[#9E958C] uppercase tracking-wider mb-3">{t.detailFundamentalsTitle}</h4>
                  {loadingDetail ? (
                    <div className="py-6 flex items-center justify-center text-xs text-[#6B645E] font-medium">{t.detailDataLoading}</div>
                  ) : detailOverview ? (
                    <div className="space-y-4">
                      {detailOverview.type === 'stock' && (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 bg-white border border-[#E8E2D9] rounded-xl p-4 text-xs font-medium">
                          <div>
                            <span className="text-[#9E958C]">{t.detailSector}</span>
                            <div className="text-[#2D2926] font-semibold">{detailOverview.sector}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailIndustry}</span>
                            <div className="text-[#2D2926] font-semibold">{detailOverview.industry}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailMarketCap}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.market_cap ? formatCurrency(detailOverview.market_cap, settings.baseCurrency) : 'N/A'}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailPE}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.pe_ratio ? detailOverview.pe_ratio.toFixed(2) : 'N/A'}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailPB}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.pb_ratio ? detailOverview.pb_ratio.toFixed(2) : 'N/A'}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailDivYield}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.dividend_yield ? `%${(detailOverview.dividend_yield * 100).toFixed(2)}` : 'N/A'}</div>
                          </div>
                          <div className="col-span-2 sm:col-span-3 pt-2 border-t border-[#E8E2D9]/40">
                            <span className="text-[#9E958C]">{t.detail52wRange}</span>
                            <div className="text-[#2D2926] font-semibold font-mono mt-0.5">
                              {detailOverview.fifty_two_week_low ? formatCurrency(detailOverview.fifty_two_week_low, settings.baseCurrency) : 'N/A'} - {detailOverview.fifty_two_week_high ? formatCurrency(detailOverview.fifty_two_week_high, settings.baseCurrency) : 'N/A'}
                            </div>
                          </div>
                        </div>
                      )}

                      {detailOverview.type === 'crypto' && (
                        <div className="grid grid-cols-2 gap-4 bg-white border border-[#E8E2D9] rounded-xl p-4 text-xs font-medium">
                          <div>
                            <span className="text-[#9E958C]">{t.detailMarketCapUSD}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.market_cap ? formatCurrency(detailOverview.market_cap, 'USD') : 'N/A'}</div>
                          </div>
                          <div>
                            <span className="text-[#9E958C]">{t.detailVolume24h}</span>
                            <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.volume_24h ? formatCurrency(detailOverview.volume_24h, 'USD') : 'N/A'}</div>
                          </div>
                          <div className="col-span-2 pt-2 border-t border-[#E8E2D9]/40">
                            <span className="text-[#9E958C]">{t.detail52wRange}</span>
                            <div className="text-[#2D2926] font-semibold font-mono mt-0.5 text-xs">
                              {detailOverview.fifty_two_week_low ? formatCurrency(detailOverview.fifty_two_week_low, 'USD') : 'N/A'} - {detailOverview.fifty_two_week_high ? formatCurrency(detailOverview.fifty_two_week_high, 'USD') : 'N/A'}
                            </div>
                          </div>
                        </div>
                      )}

                      {detailOverview.type === 'fund' && (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4 bg-white border border-[#E8E2D9] rounded-xl p-4 text-xs font-medium">
                            <div>
                              <span className="text-[#9E958C]">{t.detailFundSize}</span>
                              <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.portfolio_size ? formatCurrency(detailOverview.portfolio_size, 'TRY') : 'N/A'}</div>
                            </div>
                            <div>
                              <span className="text-[#9E958C]">{t.detailInvestorCount}</span>
                              <div className="text-[#2D2926] font-semibold font-mono">{detailOverview.investor_count ? detailOverview.investor_count.toLocaleString('tr-TR') : 'N/A'}</div>
                            </div>
                          </div>

                          {detailOverview.allocation && detailOverview.allocation.length > 0 && (
                            <div className="bg-white border border-[#E8E2D9] rounded-xl p-4">
                              <span className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-3">{t.detailFundAllocation}</span>
                              <div className="grid grid-cols-2 gap-3 text-xs font-semibold">
                                {detailOverview.allocation.map((alloc: any, idx: number) => (
                                  <div key={idx} className="flex justify-between items-center bg-[#F1EFE9]/40 p-2 rounded">
                                    <span className="text-[#6B645E]">{alloc.label}</span>
                                    <span className="font-mono text-[#2D2926]">{alloc.pct.toFixed(1)}%</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {detailOverview.description && (
                        <div className="bg-white border border-[#E8E2D9] rounded-xl p-4">
                          <span className="block text-[10px] font-bold uppercase tracking-wider text-[#9E958C] mb-2">{t.detailSummary}</span>
                          <p className="text-xs text-[#6B645E] leading-relaxed font-medium">{detailOverview.description}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-[#6B645E]/70 font-semibold border border-dashed border-[#E8E2D9] rounded-xl p-4 text-center">{t.detailNoAnalysisData}</div>
                  )}
                </div>
                </>
                )}
              </div>

              <div className="px-6 py-4 border-t border-[#E8E2D9] flex justify-end bg-[#F1EFE9]">
                <button onClick={() => setSelectedAssetForDetail(null)}
                  className="bg-[#8C9A86] hover:bg-[#7A8874] text-white px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all">
                  {t.detailClose}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
