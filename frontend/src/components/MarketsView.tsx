import React, { useState, useEffect, FormEvent, useCallback } from 'react';
import { Search, ShoppingCart, Info, TrendingUp, TrendingDown, Activity, Star, X } from 'lucide-react';
import { MarketAsset, AssetCategory, UserSettings } from '../types';
import { MARKET_ASSETS, formatCurrency, convertCurrency } from '../utils';
import { useT } from '../i18n';
import { BASE_URL, api } from '../services/api';

const WATCHLIST_KEY = 'lucrum_watchlist_v1';

interface WatchlistItem {
  symbol: string;
  name: string;
  assetClass: string;
  category: AssetCategory;
  sector: string;
  riskScore: number;
}

function loadWatchlist(): WatchlistItem[] {
  try {
    const items = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]');
    if (Array.isArray(items)) {
      const BIST_LIST = ['THYAO', 'ASELS', 'EREGL', 'GARAN', 'TUPRS', 'KCHOL', 'GESAN', 'PATEK', 'GWIND', 'CWENE', 'SDTTR',
        'AKBNK', 'ISCTR', 'SAHOL', 'SISE', 'BIMAS', 'MGROS', 'FROTO', 'TOASO', 'ARCLK', 'TCELL',
        'PGSUS', 'TAVHL', 'EKGYO', 'PETKM', 'YKBNK', 'HALKB', 'VAKBN', 'KOZAL', 'KOZAA', 'ENKAI'];
      return items.map((item: any) => {
        let ac = item.assetClass;
        const sym = (item.symbol || '').toUpperCase();
        if (ac === 'ABD Hisse/ETF' && (sym.endsWith('.IS') || BIST_LIST.includes(sym))) {
          ac = 'BIST Hissesi';
        }
        return { ...item, assetClass: ac };
      });
    }
    return [];
  } catch { return []; }
}
function saveWatchlist(items: WatchlistItem[]) {
  try { localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items)); } catch {}
}

interface MarketsViewProps {
  selectedSymbolFromSearch: string;
  setSelectedSymbolFromSearch: (symbol: string) => void;
  onAddHoldingFromMarket: (holding: {
    symbol: string; name: string; category: AssetCategory; sector: string;
    shares: number; avgBuyPrice: number; currentPrice: number; riskScore: number;
  }) => void;
  settings: UserSettings;
  exchangeRates: { usd_rate: number; eur_rate: number; gbp_rate?: number };
}

const mapToHistoryObjects = (prices: number[], baseDate = new Date()): { date: string; price: number }[] => {
  return prices.map((price, i) => {
    const d = new Date(baseDate);
    d.setDate(d.getDate() - (prices.length - 1 - i));
    return { date: d.toISOString().split('T')[0], price };
  });
};

export default function MarketsView({
  selectedSymbolFromSearch,
  setSelectedSymbolFromSearch,
  onAddHoldingFromMarket,
  settings,
  exchangeRates,
}: MarketsViewProps) {
  const t = useT(settings.language);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAsset, setSelectedAsset] = useState<MarketAsset>(MARKET_ASSETS[0]);
  const [sparkline, setSparkline] = useState<{ date: string; price: number }[]>(mapToHistoryObjects(MARKET_ASSETS[0].sparkline));
  const [buyShares, setBuyShares] = useState(10);
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});
  // Her sembolün fiyat para birimi: BIST/TEFAS → TRY, diğerleri → USD
  const [priceCurrencies, setPriceCurrencies] = useState<Record<string, string>>({});
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(loadWatchlist);
  const [watchToast, setWatchToast] = useState('');
  const [timeframe, setTimeframe] = useState<number>(30);
  const [hoveredPoint, setHoveredPoint] = useState<{ x: number; y: number; val: number; date: string; index: number } | null>(null);

  const [activeDetailTab, setActiveDetailTab] = useState<'overview' | 'fundamentals' | 'indicators' | 'profile'>('overview');
  const [fundamentals, setFundamentals] = useState<any>(null);
  const [loadingFundamentals, setLoadingFundamentals] = useState(false);
  const [indicators, setIndicators] = useState<any>(null);
  const [loadingIndicators, setLoadingIndicators] = useState(false);

  // Clear states when selected asset changes
  useEffect(() => {
    setFundamentals(null);
    setIndicators(null);
    setActiveDetailTab('overview');
  }, [selectedAsset?.symbol]);

  const fetchFundamentals = useCallback(async (symbol: string, assetClass: string) => {
    // Backend /assets/{ticker}/fundamentals ABD Hisse/ETF ve BIST Hissesi'ni destekliyor —
    // burada sadece ABD Hisse/ETF'e izin verilmesi BIST hisselerinin Temel Analiz sekmesinin
    // hiçbir zaman istek bile atmamasına (hep "Veri bulunamadı" göstermesine) yol açıyordu.
    if (assetClass !== 'ABD Hisse/ETF' && assetClass !== 'BIST Hissesi') return;
    setLoadingFundamentals(true);
    try {
      const data = await api.getAssetFundamentals(symbol, assetClass);
      setFundamentals(data);
    } catch (err) {
      console.error('Error fetching fundamentals:', err);
      setFundamentals(null);
    } finally {
      setLoadingFundamentals(false);
    }
  }, []);

  const fetchIndicators = useCallback(async (symbol: string, assetClass: string) => {
    if (assetClass !== 'ABD Hisse/ETF' && assetClass !== 'BIST Hissesi' && assetClass !== 'Kripto') return;
    setLoadingIndicators(true);
    try {
      const data = await api.getAssetIndicators(symbol, assetClass, '1day', 60);
      setIndicators(data);
    } catch (err) {
      console.error('Error fetching indicators:', err);
      setIndicators(null);
    } finally {
      setLoadingIndicators(false);
    }
  }, []);

  const handleTabChange = useCallback((tab: 'overview' | 'fundamentals' | 'indicators' | 'profile') => {
    setActiveDetailTab(tab);
    const ac = getAssetClass(selectedAsset);
    if (tab === 'fundamentals' && !fundamentals) {
      fetchFundamentals(selectedAsset.symbol, ac);
    }
    if (tab === 'indicators' && !indicators) {
      fetchIndicators(selectedAsset.symbol, ac);
    }
    if (tab === 'profile' && !fundamentals) {
      fetchFundamentals(selectedAsset.symbol, ac);
    }
  }, [selectedAsset, fundamentals, indicators, fetchFundamentals, fetchIndicators]);


  // Canlı fiyat çek — MARKET_ASSETS ilk 5 + izleme listesi
  useEffect(() => {
    const targets = [
      ...MARKET_ASSETS.slice(0, 5).map(a => ({
        symbol: a.symbol,
        assetClass: a.category === 'Crypto' ? 'Kripto' : a.category === 'FixedIncome' ? 'FixedIncome' : 'ABD Hisse/ETF',
      })),
      ...watchlist.map(w => ({ symbol: w.symbol, assetClass: w.assetClass })),
    ];
    const unique = targets.filter((t, i, arr) => arr.findIndex(x => x.symbol === t.symbol) === i);

    Promise.allSettled(
      unique.map(async ({ symbol, assetClass }) => {
        const res = await fetch(`${BASE_URL}/api/prices/${encodeURIComponent(symbol)}?asset_class=${encodeURIComponent(assetClass)}`).catch(() => null);
        if (res?.ok) {
          const d = await res.json();
          if (d?.price) return { symbol, price: d.price as number, currency: (d.price_currency ?? 'USD') as string };
        }
        return null;
      })
    ).then(results => {
      const prices: Record<string, number> = {};
      const currencies: Record<string, string> = {};
      results.forEach(r => {
        if (r.status === 'fulfilled' && r.value) {
          prices[r.value.symbol] = r.value.price;
          currencies[r.value.symbol] = r.value.currency;
        }
      });
      setLivePrices(prices);
      setPriceCurrencies(currencies);
    });
  }, [watchlist]);

  // Seçili varlık için sparkline çek
  const fetchSparkline = useCallback(async (sym: string, assetClass: string, days: number, fallback: number[]) => {
    try {
      const history = await api.getPriceHistory(sym, days, assetClass);
      if (history && history.length >= 2) {
        setSparkline(history);
      } else {
        setSparkline(mapToHistoryObjects(fallback.length >= 2 ? fallback : [fallback[0] ?? 0, fallback[0] ?? 0]));
      }
    } catch { setSparkline(mapToHistoryObjects(fallback.length >= 2 ? fallback : [fallback[0] ?? 0, fallback[0] ?? 0])); }
  }, []);

  // Header aramasından gelen sembol
  useEffect(() => {
    if (!selectedSymbolFromSearch) return;
    const sym = selectedSymbolFromSearch.toUpperCase();

    const matched = MARKET_ASSETS.find(a => a.symbol.toUpperCase() === sym);
    if (matched) {
      setSelectedAsset(matched);
      return;
    }

    api.searchAssets(sym).then(results => {
      const found = results.find(r => r.symbol.toUpperCase() === sym);
      if (!found) return;
      const assetClass = found.asset_class || 'ABD Hisse/ETF';
      fetch(`${BASE_URL}/api/prices/${encodeURIComponent(sym)}?asset_class=${encodeURIComponent(assetClass)}`)
        .then(r => r.ok ? r.json() : null)
        .then(priceData => {
          const price = priceData?.price ?? 0;
          const priceCur: string = priceData?.price_currency ?? 'USD';
          const cat: AssetCategory = found.category === 'Crypto' ? 'Crypto' : found.category === 'FixedIncome' ? 'FixedIncome' : 'Equity';
          const asset: MarketAsset = {
            symbol: found.symbol, name: found.name, category: cat, sector: found.sector,
            price, change24h: priceData?.change_pct ?? 0,
            volume24h: '—', marketCap: '—', beta: found.riskScore / 4,
            sparkline: [price, price], description: `${found.name} · ${found.asset_class}`,
          };
          setSelectedAsset(asset);
          setLivePrices(prev => ({ ...prev, [sym]: price }));
          setPriceCurrencies(prev => ({ ...prev, [sym]: priceCur }));
        }).catch(() => {});
    }).catch(() => {});
  }, [selectedSymbolFromSearch]);

  const getAssetClass = useCallback((asset: MarketAsset): string => {
    if (asset.description && asset.description.includes(' · ')) {
      const parts = asset.description.split(' · ');
      if (parts[1]) return parts[1];
    }
    if (asset.category === 'Crypto') return 'Kripto';
    if (asset.category === 'FixedIncome') return 'FixedIncome';
    
    const sym = asset.symbol.toUpperCase();
    if (sym.endsWith('.IS') || 
        ['THYAO', 'ASELS', 'EREGL', 'GARAN', 'TUPRS', 'KCHOL', 'GESAN', 'PATEK', 'GWIND', 'CWENE', 'SDTTR',
         'AKBNK', 'ISCTR', 'SAHOL', 'SISE', 'BIMAS', 'MGROS', 'FROTO', 'TOASO', 'ARCLK', 'TCELL',
         'PGSUS', 'TAVHL', 'EKGYO', 'PETKM', 'YKBNK', 'HALKB', 'VAKBN', 'KOZAL', 'KOZAA', 'ENKAI'].includes(sym)) {
      return 'BIST Hissesi';
    }
    if (['JET', 'SAS', 'TI3', 'YAS', 'KZL', 'AFA', 'AFT', 'GO2', 'GO3', 'GO4', 'YAY', 'AFV', 'BIH', 'HBU'].includes(sym)) {
      return 'TEFAS Fonu';
    }
    return 'ABD Hisse/ETF';
  }, []);

  const getAssetCurrency = useCallback((symbol: string, currentAssetClass?: string): string => {
    if (priceCurrencies[symbol]) return priceCurrencies[symbol];
    const sym = symbol.toUpperCase();
    const ac = currentAssetClass || (selectedAsset?.symbol === symbol ? getAssetClass(selectedAsset) : '');
    if (ac === 'BIST Hissesi' || ac === 'TEFAS Fonu' || sym.endsWith('.IS')) {
      return 'TRY';
    }
    return 'USD';
  }, [priceCurrencies, selectedAsset, getAssetClass]);

  // Varlık detaylarını (hacim, piyasa değeri, f/k, açıklama) arka planda yükle
  useEffect(() => {
    if (!selectedAsset?.symbol) return;
    if (selectedAsset.category === 'Cash') return;
    
    let cancelled = false;
    const ac = getAssetClass(selectedAsset);
    
    api.getAssetOverview(selectedAsset.symbol, ac)
      .then(overview => {
        if (cancelled || !overview) return;
        
        const formatLargeNum = (num: any): string => {
          if (num == null || isNaN(num)) return '—';
          const n = Number(num);
          if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
          if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
          if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
          return n.toLocaleString(settings.language === 'tr' ? 'tr-TR' : 'en-US');
        };
        
        setSelectedAsset(prev => {
          if (prev.symbol !== selectedAsset.symbol) return prev;
          
          let vol = '—';
          if (overview.volume_24h != null) vol = formatLargeNum(overview.volume_24h);
          
          let cap = '—';
          if (overview.market_cap != null) cap = formatLargeNum(overview.market_cap);
          else if (overview.portfolio_size != null) cap = formatLargeNum(overview.portfolio_size);
          
          return {
            ...prev,
            name: overview.name || prev.name,
            description: overview.description || prev.description,
            volume24h: vol,
            marketCap: cap,
            peRatio: overview.pe_ratio != null ? Number(overview.pe_ratio) : undefined,
          };
        });
      })
      .catch((err) => console.error('Error loading asset details in markets:', err));
      
    return () => { cancelled = true; };
  }, [selectedAsset.symbol, getAssetClass, settings.language]);

  // Seçili varlık değişince sparkline güncelle (izleme listesinden tıklama dahil)
  const selectAsset = useCallback((asset: MarketAsset) => {
    setSelectedAsset(asset);
    setSelectedSymbolFromSearch('');
    const ac = getAssetClass(asset);
    fetchSparkline(asset.symbol, ac, timeframe, asset.sparkline);
  }, [fetchSparkline, setSelectedSymbolFromSearch, getAssetClass, timeframe]);

  // Zaman aralığı (timeframe) değiştikçe seçili varlığın grafik geçmişini güncelle
  useEffect(() => {
    if (!selectedAsset?.symbol) return;
    const ac = getAssetClass(selectedAsset);
    fetchSparkline(selectedAsset.symbol, ac, timeframe, selectedAsset.sparkline);
  }, [timeframe, selectedAsset.symbol, getAssetClass, fetchSparkline]);

  // İzleme listesi işlemleri
  const isWatched = watchlist.some(w => w.symbol === selectedAsset.symbol);

  const toggleWatch = () => {
    let next: WatchlistItem[];
    if (isWatched) {
      next = watchlist.filter(w => w.symbol !== selectedAsset.symbol);
      setWatchToast(`${selectedAsset.symbol} izleme listesinden çıkarıldı`);
    } else {
      const item: WatchlistItem = {
        symbol: selectedAsset.symbol, name: selectedAsset.name,
        assetClass: getAssetClass(selectedAsset),
        category: selectedAsset.category, sector: selectedAsset.sector,
        riskScore: (selectedAsset.beta ?? 1) * 4,
      };
      next = [item, ...watchlist.filter(w => w.symbol !== selectedAsset.symbol)];
      setWatchToast(`${selectedAsset.symbol} izleme listesine eklendi`);
    }
    setWatchlist(next);
    saveWatchlist(next);
    setTimeout(() => setWatchToast(''), 2500);
  };

  const removeFromWatchlist = (sym: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = watchlist.filter(w => w.symbol !== sym);
    setWatchlist(next);
    saveWatchlist(next);
  };

  // Fiyatı doğru para birimiyle baseCurrency'ye çevirir
  // MARKET_ASSETS statik fiyatları USD'dir; dinamik/izleme listesi fiyatları API'den alınan currency'e göre
  const displayPrice = (symbol: string, fallbackUsd: number): number => {
    const raw = livePrices[symbol] ?? fallbackUsd;
    const cur = priceCurrencies[symbol] || getAssetCurrency(symbol);
    return convertCurrency(raw, cur, settings.baseCurrency, exchangeRates);
  };

  // Sol panel: izleme listesi + MARKET_ASSETS
  const filteredMarket = MARKET_ASSETS.filter(
    a => a.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
         a.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const filteredWatch = watchlist.filter(
    w => w.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
         w.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleBuySubmit = (e: FormEvent) => {
    e.preventDefault();
    if (buyShares <= 0) return;
    const convertedPrice = displayPrice(selectedAsset.symbol, selectedAsset.price);
    onAddHoldingFromMarket({
      symbol: selectedAsset.symbol, name: selectedAsset.name,
      category: selectedAsset.category, sector: selectedAsset.sector,
      shares: buyShares,
      avgBuyPrice: convertedPrice,
      currentPrice: convertedPrice,
      riskScore: (selectedAsset.beta ?? 1) * 4,
    });
    setShowSuccessToast(true);
    setTimeout(() => { setShowSuccessToast(false); setSelectedSymbolFromSearch(''); }, 2500);
  };

  const isUp = selectedAsset.change24h >= 0;

  // Sparkline hesabı — minimum 2 nokta garantisi
  const safeSparkline = sparkline.length >= 2 ? sparkline : mapToHistoryObjects([selectedAsset.price, selectedAsset.price]);
  const minVal = Math.min(...safeSparkline.map(h => h.price));
  const maxVal = Math.max(...safeSparkline.map(h => h.price));
  const valRange = maxVal - minVal || Math.abs(maxVal) * 0.01 || 1;

  // Zaman aralığı bazlı değişim oranı hesaplama
  const firstVal = safeSparkline[0]?.price ?? 0;
  const lastVal = safeSparkline[safeSparkline.length - 1]?.price ?? 0;
  const overallChangePct = firstVal !== 0 ? ((lastVal - firstVal) / firstVal) * 100 : 0;
  const isChartUp = overallChangePct >= 0;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center select-none">
        <div>
          <h2 className="text-xl font-bold text-[#2D2926]">{t.marketsTitle}</h2>
          <p className="text-xs text-[#6B645E] mt-0.5">{t.marketsSubtitle}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">

        {/* SOL PANEL — İzleme Listesi + Piyasalar */}
        <div id="markets-watchlist-panel" className="lg:col-span-1 bg-white border border-[#E8E2D9] p-5 rounded-2xl shadow-sm flex flex-col h-[580px]">
          <div className="relative mb-4 select-none">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9E958C] w-3.5 h-3.5" />
            <input
              type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t.searchWatchlist}
              className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-xs text-[#2D2926] rounded-lg py-1.5 pl-9 pr-3 placeholder-[#9E958C]/60 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86]"
            />
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1 pr-1 select-none">

            {/* İzleme Listesi */}
            {filteredWatch.length > 0 && (
              <>
                <div className="flex items-center gap-1.5 px-1 py-1.5">
                  <Star className="w-3 h-3 text-[#D1A86A] fill-[#D1A86A]" />
                  <span className="text-[9px] font-bold text-[#9E958C] uppercase tracking-wider">İzleme Listesi</span>
                </div>
                {filteredWatch.map(item => {
                  const active = selectedAsset.symbol === item.symbol;
                  const price = livePrices[item.symbol];
                  return (
                    <div key={item.symbol} className={`flex items-center gap-1 rounded-lg border transition-all ${active ? 'bg-[#D1A86A]/10 border-[#D1A86A]/40' : 'bg-[#F1EFE9] border-[#E8E2D9] hover:bg-[#E8E2D9]'}`}>
                      <button
                        className="flex-1 text-left p-3 flex justify-between items-center"
                        onClick={() => {
                          const marketAsset = MARKET_ASSETS.find(a => a.symbol === item.symbol);
                          if (marketAsset) { selectAsset(marketAsset); }
                          else {
                            const a: MarketAsset = {
                              symbol: item.symbol, name: item.name, category: item.category,
                              sector: item.sector, price: price ?? 0, change24h: 0,
                              volume24h: '—', marketCap: '—', beta: item.riskScore / 4,
                              sparkline: [price ?? 0, price ?? 0], description: `${item.name} · ${item.assetClass}`,
                            };
                            setSelectedAsset(a);
                            setSelectedSymbolFromSearch('');
                            fetchSparkline(item.symbol, item.assetClass, timeframe, []);
                          }
                        }}
                      >
                        <div>
                          <div className="text-xs font-bold font-mono text-[#2D2926]">{item.symbol}</div>
                          <div className="text-[10px] text-[#9E958C] truncate max-w-[110px]">{item.name}</div>
                        </div>
                        {price != null && (
                          <div className="text-right">
                            <div className="text-xs font-mono font-bold text-[#2D2926]">
                              {formatCurrency(displayPrice(item.symbol, price), settings.baseCurrency)}
                            </div>
                          </div>
                        )}
                      </button>
                      <button onClick={(e) => removeFromWatchlist(item.symbol, e)} className="p-2 text-[#D1CABF] hover:text-[#B5836F] transition-colors">
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  );
                })}
                <div className="border-t border-[#F1EFE9] my-2" />
                <div className="px-1 py-1">
                  <span className="text-[9px] font-bold text-[#9E958C] uppercase tracking-wider">Popüler</span>
                </div>
              </>
            )}

            {/* MARKET_ASSETS */}
            {filteredMarket.length > 0 ? filteredMarket.map(asset => {
              const active = selectedAsset.symbol === asset.symbol;
              const isAssetUp = asset.change24h >= 0;
              return (
                <button key={asset.symbol} onClick={() => selectAsset(asset)}
                  className={`w-full text-left p-3 rounded-lg transition-all border flex justify-between items-center ${active ? 'bg-[#8C9A86]/10 border-[#8C9A86] text-[#8C9A86]' : 'bg-[#F1EFE9] border-[#E8E2D9] text-[#6B645E] hover:bg-[#E8E2D9] hover:text-[#2D2926]'}`}
                >
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide font-mono">{asset.symbol}</div>
                    <div className="text-[10px] opacity-75 mt-0.5 font-medium truncate max-w-[140px]">{asset.name}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-mono font-bold text-[#2D2926]">
                      {formatCurrency(displayPrice(asset.symbol, asset.price), settings.baseCurrency)}
                    </div>
                    <div className={`text-[10px] font-mono font-bold mt-0.5 ${isAssetUp ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                      {isAssetUp ? '+' : ''}{asset.change24h.toFixed(2)}%
                    </div>
                  </div>
                </button>
              );
            }) : (
              <div className="text-center py-12 text-xs text-[#9E958C] font-medium">{t.noAssetsFound}</div>
            )}
          </div>
        </div>

        {/* DETAY + ALIM */}
        <div id="markets-details-panel" className="lg:col-span-2 bg-white border border-[#E8E2D9] p-6 rounded-2xl shadow-sm flex flex-col justify-between min-h-[580px] h-auto">

          {/* Başlık + Yıldız + Fiyat */}
          <div className="flex justify-between items-start select-none">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="text-lg font-bold font-mono text-[#2D2926]">{selectedAsset.symbol}</span>
                <span className="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-[#8C9A86]/10 text-[#8C9A86]">
                  {selectedAsset.category}
                </span>
                <button
                  onClick={toggleWatch}
                  title={isWatched ? 'İzleme listesinden çıkar' : 'İzleme listesine ekle'}
                  className={`p-1 rounded transition-colors ${isWatched ? 'text-[#D1A86A]' : 'text-[#D1CABF] hover:text-[#D1A86A]'}`}
                >
                  <Star className={`w-4 h-4 ${isWatched ? 'fill-[#D1A86A]' : ''}`} />
                </button>
              </div>
              <h3 className="text-sm font-semibold text-[#6B645E] mt-0.5">{selectedAsset.name}</h3>
            </div>
            <div className="text-right">
              {hoveredPoint ? (
                <div>
                  <div className={`text-lg font-bold font-mono ${isChartUp ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                    {formatCurrency(convertCurrency(hoveredPoint.val, getAssetCurrency(selectedAsset.symbol), settings.baseCurrency, exchangeRates), settings.baseCurrency)}
                  </div>
                  <div className="text-[10px] text-[#9E958C] font-semibold text-right">
                    {new Date(hoveredPoint.date).toLocaleDateString(settings.language === 'tr' ? 'tr-TR' : 'en-US', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric'
                    })}
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-lg font-bold font-mono text-[#2D2926]">
                    {formatCurrency(displayPrice(selectedAsset.symbol, selectedAsset.price), settings.baseCurrency)}
                  </div>
                  <div className={`text-xs font-mono font-bold flex items-center justify-end gap-0.5 mt-0.5 ${isChartUp ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                    {isChartUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {isChartUp ? '+' : ''}{overallChangePct.toFixed(2)}%
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Sekme Seçici */}
          <div className="flex border-b border-[#E8E2D9] mt-4 mb-3 text-xs select-none">
            {[
              { id: 'overview', label: settings.language === 'tr' ? 'Grafik' : 'Chart' },
              { id: 'fundamentals', label: settings.language === 'tr' ? 'Temel Analiz' : 'Fundamentals' },
              { id: 'indicators', label: settings.language === 'tr' ? 'Teknik Analiz' : 'Technical Indicators' },
              { id: 'profile', label: settings.language === 'tr' ? 'Şirket Kadrosu' : 'Profile & Executives' },
            ].map(tab => {
              const isActive = activeDetailTab === tab.id;
              const ac = getAssetClass(selectedAsset);
              // Backend /assets/{ticker}/fundamentals ABD Hisse/ETF ve BIST Hissesi'ni destekliyor
              // — eskiden burada sadece ABD Hisse/ETF'e izin verildiği için BIST hisselerinde
              // "Temel Analiz" ve "Şirket Kadrosu" sekmeleri hiç tıklanamıyordu (soluk/disabled).
              const isFundamentalsSupported = ac === 'ABD Hisse/ETF' || ac === 'BIST Hissesi';
              const isIndicatorSupported = ac === 'ABD Hisse/ETF' || ac === 'BIST Hissesi' || ac === 'Kripto';

              let disabled = false;
              let titleMsg = '';
              if (tab.id === 'fundamentals' || tab.id === 'profile') {
                disabled = !isFundamentalsSupported;
                if (disabled) {
                  titleMsg = settings.language === 'tr' ? 'Yalnızca ABD Hisse/ETF ve BIST için geçerli' : 'Only available for US Stocks/ETFs and BIST';
                }
              } else if (tab.id === 'indicators') {
                disabled = !isIndicatorSupported;
                if (disabled) {
                  titleMsg = settings.language === 'tr' ? 'Yalnızca ABD, BIST ve Kripto için geçerli' : 'Only available for US, BIST, and Crypto';
                }
              }

              return (
                <button
                  key={tab.id}
                  disabled={disabled}
                  onClick={() => handleTabChange(tab.id as any)}
                  className={`pb-2 px-3 font-bold border-b-2 transition-all -mb-[2px] ${
                    disabled
                      ? 'text-[#D1CABF] border-transparent cursor-not-allowed opacity-40'
                      : isActive
                      ? 'border-[#8C9A86] text-[#2D2926]'
                      : 'border-transparent text-[#9E958C] hover:text-[#2D2926]'
                  }`}
                  title={titleMsg}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* SEKME İÇERİKLERİ */}
          <div className="flex-1 flex flex-col justify-between">
            {activeDetailTab === 'overview' && (
              <div className="flex flex-col justify-between flex-1">
                {/* Zaman Aralığı Seçici */}
                {selectedAsset.category !== 'Cash' && (
                  <div className="flex justify-end mb-1 select-none">
                    <div className="flex bg-[#F1EFE9] border border-[#E8E2D9] rounded-lg p-0.5 text-[9px] font-bold uppercase tracking-wider">
                      {[
                        { label: settings.language === 'tr' ? '1A' : '1M', value: 30 },
                        { label: settings.language === 'tr' ? '3A' : '3M', value: 90 },
                        { label: settings.language === 'tr' ? '6A' : '6M', value: 180 },
                        { label: settings.language === 'tr' ? '1Y' : '1Y', value: 365 },
                        { label: settings.language === 'tr' ? '2Y' : '2Y', value: 730 },
                      ].map(opt => (
                        <button
                          key={opt.value}
                          onClick={() => setTimeframe(opt.value)}
                          className={`px-2.5 py-1 rounded-md transition-all ${timeframe === opt.value ? 'bg-white text-[#2D2926] shadow-sm' : 'text-[#9E958C] hover:text-[#2D2926]'}`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sparkline */}
                <div className="my-4 h-32 border-b border-[#E8E2D9] pb-4 relative select-none">
                  {(() => {
                    const stepX = 400 / Math.max(safeSparkline.length - 1, 1);
                    const PAD_T = 10;
                    const coordsPadded = safeSparkline.map((h, idx) => ({
                      x: idx * stepX,
                      y: PAD_T + 80 - ((h.price - minVal) / valRange) * 80,
                      val: h.price,
                      date: h.date,
                      index: idx
                    }));
                    const pathDPadded = coordsPadded.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
                    const fillPathPadded = `${pathDPadded} L400,110 L0,110 Z`;

                    return (
                      <>
                        <svg
                          className="w-full h-full overflow-visible"
                          viewBox="0 0 400 110"
                          preserveAspectRatio="none"
                          onMouseMove={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect();
                            const mouseX = e.clientX - rect.left;
                            const pct = mouseX / rect.width;
                            const idx = Math.max(0, Math.min(coordsPadded.length - 1, Math.round(pct * (coordsPadded.length - 1))));
                            setHoveredPoint(coordsPadded[idx]);
                          }}
                          onMouseLeave={() => setHoveredPoint(null)}
                        >
                          <defs>
                            <linearGradient id="greenGrad" x1="0%" x2="0%" y1="0%" y2="100%">
                              <stop offset="0%" stopColor="#7A8874" /><stop offset="100%" stopColor="#7A8874" stopOpacity="0" />
                            </linearGradient>
                            <linearGradient id="redGrad" x1="0%" x2="0%" y1="0%" y2="100%">
                              <stop offset="0%" stopColor="#B5836F" /><stop offset="100%" stopColor="#B5836F" stopOpacity="0" />
                            </linearGradient>
                          </defs>
                          
                          <path d={fillPathPadded} fill={isChartUp ? 'url(#greenGrad)' : 'url(#redGrad)'} opacity="0.12" />
                          <path d={pathDPadded} fill="none" stroke={isChartUp ? '#7A8874' : '#B5836F'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

                          {hoveredPoint && (
                            <g>
                              <line
                                x1={hoveredPoint.x} y1={PAD_T} x2={hoveredPoint.x} y2={90}
                                stroke={isChartUp ? '#7A8874' : '#B5836F'} strokeWidth="1" strokeDasharray="3,3" opacity="0.6"
                              />
                              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="5" fill={isChartUp ? '#7A8874' : '#B5836F'} opacity="0.2" />
                              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="3" fill={isChartUp ? '#7A8874' : '#B5836F'} />
                              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="1.2" fill="white" />
                            </g>
                          )}
                        </svg>
                      </>
                    );
                  })()}
                  <div className="absolute left-0 bottom-1.5 text-[9px] uppercase font-bold text-[#9E958C] tracking-wider">
                    {safeSparkline.length > 7 
                      ? (settings.language === 'tr' ? `${safeSparkline.length}g geçmiş` : `${safeSparkline.length}d history`) 
                      : t.historicTrend}
                  </div>
                </div>

                {/* Metadata */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 select-none mb-4">
                  {[
                    { label: t.volume24h, value: selectedAsset.volume24h },
                    { label: t.marketCap, value: selectedAsset.marketCap },
                    { label: t.peRatio, value: selectedAsset.peRatio ? selectedAsset.peRatio.toFixed(1) : 'N/A' },
                    { label: t.beta, value: (selectedAsset.beta ?? 1).toFixed(2) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-[#F1EFE9] border border-[#E8E2D9] p-2.5 rounded-lg">
                      <span className="text-[10px] text-[#9E958C] block font-bold uppercase tracking-wider">{label}</span>
                      <span className="text-xs font-mono font-bold text-[#2D2926] mt-0.5 block">{value}</span>
                    </div>
                  ))}
                </div>

                {/* Açıklama */}
                <div className="text-xs text-[#6B645E] font-medium leading-relaxed bg-[#F1EFE9] border border-[#E8E2D9] p-3.5 rounded-lg flex gap-3 select-none mb-4">
                  <Info className="w-4 h-4 text-[#8C9A86] shrink-0 mt-0.5" />
                  <p className="opacity-90 line-clamp-2">{selectedAsset.description}</p>
                </div>
              </div>
            )}

            {activeDetailTab === 'fundamentals' && (
              <div className="flex-1 flex flex-col gap-4 text-xs overflow-y-auto max-h-[360px] pr-1 custom-scrollbar">
                {loadingFundamentals ? (
                  <div className="flex flex-col items-center justify-center py-20">
                    <div className="w-6 h-6 border-2 border-[#8C9A86] border-t-transparent rounded-full animate-spin mb-2" />
                    <span className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider">
                      {settings.language === 'tr' ? 'Finansallar Yükleniyor...' : 'Loading Fundamentals...'}
                    </span>
                  </div>
                ) : fundamentals ? (
                  <>
                    {/* Rasyolar Grid */}
                    <div>
                      <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] mb-2 text-[#8C9A86]">
                        {settings.language === 'tr' ? 'Finansal Oranlar (Valuation)' : 'Valuation Ratios'}
                      </h4>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {[
                          { label: settings.language === 'tr' ? 'F/K (Geçmiş)' : 'P/E (Trailing)', val: fundamentals.statistics?.pe_trailing },
                          { label: settings.language === 'tr' ? 'F/K (İleri)' : 'P/E (Forward)', val: fundamentals.statistics?.pe_forward },
                          { label: settings.language === 'tr' ? 'PEG Oranı' : 'PEG Ratio', val: fundamentals.statistics?.peg_ratio },
                          { label: settings.language === 'tr' ? 'Fiyat/Satış' : 'Price/Sales', val: fundamentals.statistics?.ps_ratio },
                          { label: settings.language === 'tr' ? 'Fiyat/Defter' : 'Price/Book', val: fundamentals.statistics?.pb_ratio },
                          { label: settings.language === 'tr' ? 'Özkaynak Kârlılığı (ROE)' : 'Return on Equity (ROE)', val: fundamentals.statistics?.roe ? `${(fundamentals.statistics.roe * 100).toFixed(1)}%` : null },
                          { label: settings.language === 'tr' ? 'Aktif Kârlılığı (ROA)' : 'Return on Assets (ROA)', val: fundamentals.statistics?.roa ? `${(fundamentals.statistics.roa * 100).toFixed(1)}%` : null },
                          { label: settings.language === 'tr' ? 'Net Kâr Marjı' : 'Profit Margin', val: fundamentals.statistics?.profit_margin ? `${(fundamentals.statistics.profit_margin * 100).toFixed(1)}%` : null },
                          { label: settings.language === 'tr' ? 'Faaliyet Marjı' : 'Operating Margin', val: fundamentals.statistics?.operating_margin ? `${(fundamentals.statistics.operating_margin * 100).toFixed(1)}%` : null },
                        ].map(item => (
                          <div key={item.label} className="bg-[#F1EFE9] border border-[#E8E2D9] p-2 rounded-lg flex justify-between items-center">
                            <span className="text-[10px] text-[#9E958C] font-semibold">{item.label}</span>
                            <span className="font-mono font-bold text-[#2D2926]">{item.val ?? '—'}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Bilanço Tablosu */}
                    {fundamentals.balance_sheet && fundamentals.balance_sheet.length > 0 && (
                      <div>
                        <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] mb-2 text-[#8C9A86]">
                          {settings.language === 'tr' ? 'Çeyreklik Bilanço Özet (Milyon USD)' : 'Quarterly Balance Sheet (M USD)'}
                        </h4>
                        <div className="overflow-x-auto border border-[#E8E2D9] rounded-lg">
                          <table className="w-full text-left text-[10px] border-collapse">
                            <thead>
                              <tr className="bg-[#F1EFE9] text-[#6B645E] font-bold border-b border-[#E8E2D9]">
                                <th className="p-2">{settings.language === 'tr' ? 'Dönem' : 'Period'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Aktifler' : 'Assets'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Borçlar' : 'Liabilities'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Özkaynak' : 'Equity'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Nakit' : 'Cash'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Borç' : 'Debt'}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {fundamentals.balance_sheet.slice(0, 4).map((row: any) => (
                                <tr key={row.fiscal_date} className="border-b border-[#E8E2D9] text-[#4A443F] font-mono">
                                  <td className="p-2 font-bold">{row.fiscal_date}</td>
                                  <td className="p-2">{(row.total_assets / 1e6).toFixed(0)}</td>
                                  <td className="p-2">{(row.total_liab / 1e6).toFixed(0)}</td>
                                  <td className="p-2 font-bold text-[#7A8874]">{(row.total_equity / 1e6).toFixed(0)}</td>
                                  <td className="p-2">{(row.cash / 1e6).toFixed(0)}</td>
                                  <td className="p-2 text-[#B5836F]">{(row.total_debt / 1e6).toFixed(0)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* EPS Kazanç Tablosu */}
                    {fundamentals.earnings && fundamentals.earnings.length > 0 && (
                      <div>
                        <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] mb-2 text-[#8C9A86]">
                          {settings.language === 'tr' ? 'EPS Çeyreklik Kazanç Sürprizleri' : 'Quarterly EPS Performance'}
                        </h4>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                          {fundamentals.earnings.slice(0, 4).map((earn: any) => {
                            const isPositive = earn.surprise_pct >= 0;
                            return (
                              <div key={earn.date} className="bg-[#F9F7F2] border border-[#E8E2D9] p-2 rounded-lg flex flex-col justify-between">
                                <div className="text-[9px] text-[#9E958C] font-bold">{earn.date}</div>
                                <div className="flex justify-between items-center mt-1">
                                  <span className="text-[10px] text-[#6B645E]">{settings.language === 'tr' ? 'Bekl/Gerçek' : 'Est/Act'}</span>
                                  <span className="font-mono font-bold text-[#2D2926]">
                                    {earn.eps_estimate ?? '—'} / {earn.eps_actual ?? '—'}
                                  </span>
                                </div>
                                <div className={`text-[9px] font-bold text-right mt-1 ${isPositive ? 'text-[#7A8874]' : 'text-[#B5836F]'}`}>
                                  {isPositive ? '▲' : '▼'} {earn.surprise_pct ? `${earn.surprise_pct.toFixed(1)}%` : '—'}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-12 text-xs text-[#9E958C]">{settings.language === 'tr' ? 'Veri bulunamadı.' : 'No data available.'}</div>
                )}
              </div>
            )}

            {activeDetailTab === 'indicators' && (
              <div className="flex-1 flex flex-col gap-4 overflow-y-auto max-h-[360px] pr-1 custom-scrollbar text-xs">
                {loadingIndicators ? (
                  <div className="flex flex-col items-center justify-center py-20">
                    <div className="w-6 h-6 border-2 border-[#8C9A86] border-t-transparent rounded-full animate-spin mb-2" />
                    <span className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider">
                      {settings.language === 'tr' ? 'Teknik Analiz Yükleniyor...' : 'Loading Technical Indicators...'}
                    </span>
                  </div>
                ) : indicators ? (
                  <div className="flex flex-col gap-6">
                    {/* RSI(14) Grafiği */}
                    {indicators.rsi && indicators.rsi.length > 0 && (
                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] text-[#8C9A86]">
                            RSI (14)
                          </h4>
                          <span className="font-mono font-bold text-xs text-[#2D2926]">
                            {(indicators.rsi[0]?.rsi ?? indicators.rsi[0]?.v1)?.toFixed(1) ?? '—'}
                          </span>
                        </div>
                        <div className="h-28 bg-[#F1EFE9] border border-[#E8E2D9] rounded-lg p-2 relative overflow-visible">
                          {(() => {
                            const rsiValues = [...indicators.rsi].reverse();
                            const stepX = 380 / Math.max(rsiValues.length - 1, 1);
                            
                            // Convert RSI (0-100) to height (0-90)
                            const coords = rsiValues.map((pt, idx) => {
                              const rsiVal = pt.rsi ?? pt.v1;
                              return {
                                x: idx * stepX,
                                y: 90 - (rsiVal / 100) * 80,
                                val: rsiVal,
                                date: pt.dt
                              };
                            });
                            
                            const rsiPath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
                            
                            // Reference lines coordinates
                            const y70 = 90 - (70 / 100) * 80;
                            const y30 = 90 - (30 / 100) * 80;
                            
                            return (
                              <svg className="w-full h-full overflow-visible" viewBox="0 0 380 90" preserveAspectRatio="none">
                                {/* Overbought 70 line */}
                                <line x1="0" y1={y70} x2="380" y2={y70} stroke="#B5836F" strokeDasharray="3,3" strokeWidth="1" opacity="0.6" />
                                <text x="5" y={y70 - 2} fill="#B5836F" className="text-[7px] font-bold font-mono">70</text>
                                
                                {/* Oversold 30 line */}
                                <line x1="0" y1={y30} x2="380" y2={y30} stroke="#7A8874" strokeDasharray="3,3" strokeWidth="1" opacity="0.6" />
                                <text x="5" y={y30 + 7} fill="#7A8874" className="text-[7px] font-bold font-mono">30</text>
                                
                                {/* RSI Line */}
                                <path d={rsiPath} fill="none" stroke="#8C9A86" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            );
                          })()}
                        </div>
                      </div>
                    )}

                    {/* MACD Grafiği */}
                    {indicators.macd && indicators.macd.length > 0 && (
                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] text-[#8C9A86]">
                            MACD (12, 26, 9)
                          </h4>
                          <div className="flex gap-3 font-mono text-[9px] font-bold">
                            <span className="text-[#8C9A86]">MACD: {(indicators.macd[0]?.macd ?? indicators.macd[0]?.v1)?.toFixed(3) ?? '—'}</span>
                            <span className="text-[#D1A86A]">Signal: {(indicators.macd[0]?.macd_signal ?? indicators.macd[0]?.v2)?.toFixed(3) ?? '—'}</span>
                            <span className={(indicators.macd[0]?.macd_hist ?? indicators.macd[0]?.v3) >= 0 ? 'text-[#7A8874]' : 'text-[#B5836F]'}>
                              Hist: {(indicators.macd[0]?.macd_hist ?? indicators.macd[0]?.v3)?.toFixed(3) ?? '—'}
                            </span>
                          </div>
                        </div>
                        <div className="h-32 bg-[#F1EFE9] border border-[#E8E2D9] rounded-lg p-2 relative overflow-visible">
                          {(() => {
                            // Backend hem semantik alan adları (macd/macd_signal/macd_hist) hem de
                            // eski/geriye dönük uyumlu cache satırlarından gelen v1/v2/v3 döndürebiliyor.
                            const macdValues = [...indicators.macd].reverse().map((pt: any) => ({
                              dt: pt.dt,
                              macd: pt.macd ?? pt.v1,
                              macd_signal: pt.macd_signal ?? pt.v2,
                              macd_hist: pt.macd_hist ?? pt.v3,
                            }));
                            const stepX = 380 / Math.max(macdValues.length - 1, 1);
                            
                            // Find absolute max value for MACD lines & histogram to scale properly
                            const allVals = macdValues.flatMap(d => [d.macd, d.macd_signal, d.macd_hist].filter(v => v != null));
                            const maxAbs = Math.max(...allVals.map(Math.abs), 0.01) * 1.1;

                            const scaleY = (v: number) => {
                              // Centered around 50 (middle of height 100)
                              return 50 - (v / maxAbs) * 45;
                            };

                            const macdCoords = macdValues.map((pt, idx) => ({ x: idx * stepX, y: scaleY(pt.macd) }));
                            const signalCoords = macdValues.map((pt, idx) => ({ x: idx * stepX, y: scaleY(pt.macd_signal) }));
                            
                            const macdPath = macdCoords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
                            const signalPath = signalCoords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
                            
                            const zeroY = scaleY(0);
                            
                            return (
                              <svg className="w-full h-full overflow-visible" viewBox="0 0 380 100" preserveAspectRatio="none">
                                {/* Zero reference line */}
                                <line x1="0" y1={zeroY} x2="380" y2={zeroY} stroke="#9E958C" strokeWidth="1" opacity="0.3" />
                                
                                {/* MACD Histogram Bars */}
                                {macdValues.map((pt, idx) => {
                                  const barX = idx * stepX;
                                  const barY = scaleY(pt.macd_hist);
                                  const isPos = pt.macd_hist >= 0;
                                  return (
                                    <rect
                                      key={idx}
                                      x={barX - 1.5}
                                      y={isPos ? barY : zeroY}
                                      width="3"
                                      height={Math.max(0.5, Math.abs(barY - zeroY))}
                                      fill={isPos ? '#7A8874' : '#B5836F'}
                                      opacity="0.6"
                                    />
                                  );
                                })}
                                
                                {/* MACD Line */}
                                <path d={macdPath} fill="none" stroke="#8C9A86" strokeWidth="1.5" />
                                
                                {/* Signal Line */}
                                <path d={signalPath} fill="none" stroke="#D1A86A" strokeWidth="1.5" />
                              </svg>
                            );
                          })()}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-12 text-xs text-[#9E958C]">{settings.language === 'tr' ? 'Veri bulunamadı.' : 'No data available.'}</div>
                )}
              </div>
            )}

            {activeDetailTab === 'profile' && (
              <div className="flex-1 flex flex-col gap-4 text-xs overflow-y-auto max-h-[360px] pr-1 custom-scrollbar">
                {loadingFundamentals ? (
                  <div className="flex flex-col items-center justify-center py-20">
                    <div className="w-6 h-6 border-2 border-[#8C9A86] border-t-transparent rounded-full animate-spin mb-2" />
                    <span className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider">
                      {settings.language === 'tr' ? 'Profil Yükleniyor...' : 'Loading Profile...'}
                    </span>
                  </div>
                ) : fundamentals?.profile ? (
                  <>
                    {/* Şiriket Künyesi */}
                    <div className="grid grid-cols-2 gap-2.5">
                      {[
                        { label: settings.language === 'tr' ? 'CEO' : 'CEO', value: fundamentals.profile.ceo },
                        { label: settings.language === 'tr' ? 'Sektör' : 'Sector', value: fundamentals.profile.sector },
                        { label: settings.language === 'tr' ? 'Endüstri' : 'Industry', value: fundamentals.profile.industry },
                        { label: settings.language === 'tr' ? 'Çalışan Sayısı' : 'Employees', value: fundamentals.profile.employees?.toLocaleString() },
                        { label: settings.language === 'tr' ? 'Web Sitesi' : 'Website', value: fundamentals.profile.website, isLink: true },
                        { label: settings.language === 'tr' ? 'Borsa' : 'Exchange', value: fundamentals.profile.exchange },
                      ].map(item => (
                        <div key={item.label} className="bg-[#F1EFE9] border border-[#E8E2D9] p-2.5 rounded-lg">
                          <span className="text-[9px] text-[#9E958C] block font-bold uppercase tracking-wider">{item.label}</span>
                          {item.isLink && item.value ? (
                            <a
                              href={item.value.startsWith('http') ? item.value : `https://${item.value}`}
                              target="_blank" rel="noopener noreferrer"
                              className="text-[11px] font-bold text-[#8C9A86] hover:underline block truncate mt-0.5"
                            >
                              {item.value}
                            </a>
                          ) : (
                            <span className="text-[11px] font-bold text-[#2D2926] block truncate mt-0.5">{item.value ?? '—'}</span>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Detaylı Açıklama */}
                    <div>
                      <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] mb-1.5 text-[#8C9A86]">
                        {settings.language === 'tr' ? 'İş Özeti' : 'Business Summary'}
                      </h4>
                      <p className="text-xs text-[#6B645E] bg-[#F1EFE9] border border-[#E8E2D9] p-3 rounded-lg leading-relaxed select-text">
                        {fundamentals.profile.description}
                      </p>
                    </div>

                    {/* Yönetim Kurulu / Yöneticiler */}
                    {fundamentals.executives && fundamentals.executives.length > 0 && (
                      <div>
                        <h4 className="font-bold text-[#2D2926] uppercase tracking-wider text-[10px] mb-1.5 text-[#8C9A86]">
                          {settings.language === 'tr' ? 'Kilit Yöneticiler' : 'Key Executives'}
                        </h4>
                        <div className="overflow-x-auto border border-[#E8E2D9] rounded-lg">
                          <table className="w-full text-left text-[10px] border-collapse">
                            <thead>
                              <tr className="bg-[#F1EFE9] text-[#6B645E] font-bold border-b border-[#E8E2D9]">
                                <th className="p-2">{settings.language === 'tr' ? 'İsim' : 'Name'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Unvan' : 'Title'}</th>
                                <th className="p-2">{settings.language === 'tr' ? 'Yaş' : 'Age'}</th>
                                <th className="p-2 text-right">{settings.language === 'tr' ? 'Maaş' : 'Pay'}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {fundamentals.executives.map((exec: any) => (
                                <tr key={exec.name} className="border-b border-[#E8E2D9] text-[#4A443F]">
                                  <td className="p-2 font-bold text-[#2D2926]">{exec.name}</td>
                                  <td className="p-2 font-semibold text-[#6B645E]">{exec.title}</td>
                                  <td className="p-2 font-mono">{exec.age ?? '—'}</td>
                                  <td className="p-2 font-mono text-right">
                                    {exec.pay ? `$${(exec.pay / 1e6).toFixed(2)}M` : '—'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-12 text-xs text-[#9E958C]">{settings.language === 'tr' ? 'Veri bulunamadı.' : 'No data available.'}</div>
                )}
              </div>
            )}

            {/* Alım Formu */}
            <form onSubmit={handleBuySubmit} className="border-t border-[#E8E2D9] pt-4 mt-4 flex items-center justify-between flex-wrap gap-4 select-none">
              <div className="flex items-center gap-3">
                <label className="text-xs font-bold text-[#6B645E] uppercase tracking-wider shrink-0">{t.logPurchase}</label>
                <input
                  type="number" step="any" min="0.001" required value={buyShares}
                  onChange={(e) => setBuyShares(Number(e.target.value))}
                  className="bg-[#F1EFE9] border border-[#E8E2D9] text-xs font-mono font-bold text-[#2D2926] rounded-lg py-1.5 px-3 w-24 text-center focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86]"
                />
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <span className="text-[9px] uppercase font-bold text-[#9E958C] block tracking-wider">{t.outlayTotal}</span>
                  <span className="text-sm font-mono font-bold text-[#2D2926]">
                    {formatCurrency(buyShares * displayPrice(selectedAsset.symbol, selectedAsset.price), settings.baseCurrency)}
                  </span>
                </div>
                <button type="submit"
                  className="flex items-center gap-1.5 bg-[#8C9A86] hover:bg-[#7A8874] text-white px-5 py-2 rounded-full text-xs font-bold uppercase tracking-wider transition-all shadow-sm"
                >
                  <ShoppingCart className="w-3.5 h-3.5" />
                  {t.executeBuy}
                </button>
              </div>
            </form>
          </div>
        </div>

      </div>

      {/* Toast — alım */}
      {showSuccessToast && (
        <div className="fixed bottom-6 right-6 bg-[#7A8874] text-white border border-[#8C9A86] rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3 z-50 font-bold text-sm">
          <Activity className="w-4 h-4 animate-bounce" />
          <span>{t.buySuccess(buyShares, selectedAsset.symbol)}</span>
        </div>
      )}

      {/* Toast — izleme listesi */}
      {watchToast && (
        <div className="fixed bottom-6 right-6 bg-[#2D2926] text-white rounded-xl px-5 py-3 shadow-2xl flex items-center gap-3 z-50 text-sm font-semibold">
          <Star className="w-4 h-4 text-[#D1A86A] fill-[#D1A86A]" />
          <span>{watchToast}</span>
        </div>
      )}
    </div>
  );
}
