import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Newspaper, RefreshCw, ExternalLink, Clock, TrendingUp, PieChart, ChevronDown, ChevronUp, Wifi } from 'lucide-react';
import { Holding, NewsArticle, UserSettings } from '../types';
import { api } from '../services/api';

const TEFAS_TICKERS = new Set([
  'JET','SAS','TI3','YAS','KZL','AFA','AFT','GO2','GO3','GO4',
  'YAY','AFV','BIH','HBU','AK1','MAC','TCD','GAF','YEF','GBG',
  'IPJ','ZZL','AKB','GAG','HEF','TI2','IYF','KBF','YKY','TYH',
]);

const ALLOCATION_COLORS = [
  '#8C9A86','#A8B89E','#6B7E65','#C4D4BC','#4A5E44',
  '#D4A96A','#B8860B','#9E7B3A','#6B8CAE','#4A7090',
];

interface FundBreakdown {
  fund_code: string; fund_name: string; date: string;
  price: number | null; portfolio_size: number | null;
  investor_count: number | null;
  allocation: { label: string; pct: number }[];
}

interface MacroItem {
  tag: string; title: string; url: string; source: string; published_at: string;
}

interface NewsViewProps {
  holdings: Holding[];
  settings: UserSettings;
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr.slice(0, 10);
    const mins = Math.floor((Date.now() - date.getTime()) / 60000);
    if (mins < 1) return 'Az önce';
    if (mins < 60) return `${mins}d`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}s`;
    return `${Math.floor(hrs / 24)}g`;
  } catch { return ''; }
}

function sourceInitial(source: string): string {
  return source ? source.charAt(0).toUpperCase() : '?';
}

function sourceAccent(source: string): string {
  if (source === 'KAP') return '#B5836F';
  if (source.includes('Yahoo')) return '#7B68EE';
  if (source.includes('Reuters')) return '#E8731A';
  if (source.includes('Bloomberg')) return '#5B8DB8';
  return '#8C9A86';
}

function FundMiniCard({ fundCode, isEn }: { fundCode: string; isEn: boolean; key?: any }) {
  const [data, setData] = useState<FundBreakdown | null>(null);
  const [open, setOpen] = useState(false);
  const [disclosures, setDisclosures] = useState<{ title: string; publish_date: string; url: string }[]>([]);

  useEffect(() => {
    api.getFundBreakdown(fundCode).then(setData).catch((err) => console.error(`Fund breakdown fetch failed for ${fundCode}:`, err));
    api.getFundDisclosures(fundCode).then(r => setDisclosures(r.disclosures?.slice(0,4) || [])).catch((err) => console.error(`Fund disclosures fetch failed for ${fundCode}:`, err));
  }, [fundCode]);

  if (!data || !data.allocation.length) return null;
  const fmt = (n: number | null) => n == null ? '—' : n >= 1e9 ? `${(n/1e9).toFixed(1)}B ₺` : n >= 1e6 ? `${(n/1e6).toFixed(0)}M ₺` : `${n.toLocaleString('tr-TR')} ₺`;

  return (
    <div className="bg-white border border-[#E8E2D9] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#F9F7F2] transition-colors"
      >
        <div className="flex items-center gap-2">
          <PieChart className="w-3.5 h-3.5 text-[#8C9A86]" />
          <span className="text-xs font-bold text-[#2D2926]">{fundCode}</span>
          <span className="text-[10px] text-[#9E958C] truncate max-w-[140px]">{data.fund_name}</span>
        </div>
        {open ? <ChevronUp className="w-3.5 h-3.5 text-[#9E958C]" /> : <ChevronDown className="w-3.5 h-3.5 text-[#9E958C]" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t border-[#F1EFE9]">
              <div className="flex justify-between pt-3 text-[10px] text-[#9E958C]">
                {data.price != null && <span>{isEn ? 'Price: ' : 'Fiyat: '}<b className="text-[#2D2926]">₺{data.price.toFixed(4)}</b></span>}
                {data.portfolio_size != null && <span>{isEn ? 'Size: ' : 'Büyüklük: '}<b className="text-[#2D2926]">{fmt(data.portfolio_size)}</b></span>}
              </div>
              <div className="space-y-1.5">
                {data.allocation.slice(0, 6).map((item, i) => (
                  <div key={item.label} className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }} />
                    <span className="text-[10px] text-[#4A443F] flex-1 truncate">{item.label}</span>
                    <span className="text-[10px] font-bold text-[#2D2926]">%{item.pct.toFixed(1)}</span>
                  </div>
                ))}
              </div>
              {disclosures.length > 0 && (
                <div className="pt-2 border-t border-[#F1EFE9] space-y-1.5">
                  <p className="text-[10px] font-bold text-[#9E958C] uppercase tracking-wider">{isEn ? 'KAP Disclosures' : 'KAP Bildirimleri'}</p>
                  {disclosures.map((d, i) => (
                    <a key={i} href={d.url} target="_blank" rel="noopener noreferrer"
                      className="flex items-start gap-1.5 group"
                    >
                      <ExternalLink className="w-2.5 h-2.5 text-[#D1CABF] group-hover:text-[#8C9A86] shrink-0 mt-0.5" />
                      <span className="text-[10px] text-[#6B645E] group-hover:text-[#8C9A86] line-clamp-1 transition-colors">{d.title || d.publish_date}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface AiNewsSummary {
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  whatHappened: string;
  howItAffectsMe: string;
}

function generateMockAiSummary(title: string, ticker: string, isEn: boolean): AiNewsSummary {
  const t = ticker.toUpperCase();
  const lowerTitle = title.toLowerCase();
  
  let sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' = 'NEUTRAL';
  if (
    lowerTitle.includes('up') || lowerTitle.includes('rise') || lowerTitle.includes('gain') || 
    lowerTitle.includes('rekor') || lowerTitle.includes('kazan') || lowerTitle.includes('artış') || 
    lowerTitle.includes('büyü') || lowerTitle.includes('kar') || lowerTitle.includes('kâr') ||
    lowerTitle.includes('positive') || lowerTitle.includes('pozitif')
  ) {
    sentiment = 'POSITIVE';
  } else if (
    lowerTitle.includes('down') || lowerTitle.includes('fall') || lowerTitle.includes('loss') || 
    lowerTitle.includes('düşüş') || lowerTitle.includes('kayıp') || lowerTitle.includes('zarar') || 
    lowerTitle.includes('risk') || lowerTitle.includes('negative') || lowerTitle.includes('negatif')
  ) {
    sentiment = 'NEGATIVE';
  }
  
  if (isEn) {
    return {
      sentiment,
      whatHappened: `AI Simplified: A major event or earnings update reported for ${t} regarding '${title.slice(0, 55)}...'.`,
      howItAffectsMe: sentiment === 'POSITIVE'
        ? `Positive momentum detected for ${t}. This could support short-term price valuation. Holding is recommended.`
        : sentiment === 'NEGATIVE'
        ? `Risk factors identified for ${t}. Monitor volatility closely; hedging or review may be beneficial.`
        : `No direct immediate impact on ${t}. Recommended action: Keep monitoring for macro triggers.`
    };
  } else {
    return {
      sentiment,
      whatHappened: `AI Özet: ${t} için '${title.slice(0, 55)}...' konusu hakkında karmaşık terimlerden arındırılmış sadeleştirilmiş özet.`,
      howItAffectsMe: sentiment === 'POSITIVE'
        ? `${t} için pozitif momentum tespit edildi. Kısa vadeli fiyatlanmayı destekleyebilir; pozisyonun korunması önerilir.`
        : sentiment === 'NEGATIVE'
        ? `${t} için olası olumsuz risk faktörleri tespit edildi. Oynaklık yakından izlenmeli, gerekirse koruma planları değerlendirilmeli.`
        : `${t} üzerinde ani ve doğrudan bir etki beklenmiyor. Mevcut pozisyon takibine devam edilmesi önerilir.`
    };
  }
}

function ArticleCard({ article, featured = false, isEn }: { article: NewsArticle; featured?: boolean; isEn: boolean }) {
  const accent = sourceAccent(article.source);
  const [showAiSummary, setShowAiSummary] = useState(false);

  const renderAiSummaryPanel = () => {
    if (!showAiSummary) return null;
    const summary = generateMockAiSummary(article.title, article.ticker, isEn);
    const sentColor = summary.sentiment === 'POSITIVE' 
      ? 'text-[#7A8874] bg-[#7A8874]/10 border-[#7A8874]/20' 
      : summary.sentiment === 'NEGATIVE' 
      ? 'text-[#B5836F] bg-[#B5836F]/10 border-[#B5836F]/20' 
      : 'text-[#9E958C] bg-[#F1EFE9] border-[#E8E2D9]';
    const sentText = summary.sentiment === 'POSITIVE' 
      ? (isEn ? 'POSITIVE' : 'OLUMLU') 
      : summary.sentiment === 'NEGATIVE' 
      ? (isEn ? 'NEGATIVE' : 'OLUMSUZ') 
      : (isEn ? 'NEUTRAL' : 'NÖTR');

    return (
      <div className="mt-3 bg-[#FBF9F6] border border-[#E8E2D9] rounded-xl p-3 space-y-2 text-left animate-fade-in">
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-bold text-[#8A5A36] uppercase tracking-wider">✨ AI INSIGHT</span>
          <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded border ${sentColor}`}>{sentText}</span>
        </div>
        <div className="space-y-1.5 text-[10px] leading-relaxed">
          <p className="text-[#2D2926] font-semibold">
            <span className="text-[#8C9A86] mr-1">●</span>{summary.whatHappened}
          </p>
          <p className="text-[#6B645E]">
            <span className="text-[#8A5A36] mr-1">●</span>
            <b>{isEn ? 'Portfolio Impact:' : 'Portföy Etkisi:'}</b> {summary.howItAffectsMe}
          </p>
        </div>
      </div>
    );
  };

  if (featured) {
    return (
      <div className="group block bg-white border border-[#E8E2D9] rounded-2xl p-6 hover:border-[#8C9A86] hover:shadow-md transition-all">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0"
            style={{ backgroundColor: accent }}>
            {sourceInitial(article.source)}
          </div>
          <span className="text-[10px] font-semibold text-[#9E958C]">{article.source}</span>
          <span className="text-[#E8E2D9]">·</span>
          <span className="text-[10px] font-bold text-[#8C9A86] uppercase tracking-wide px-2 py-0.5 bg-[#8C9A86]/10 rounded-full">
            {article.ticker}
          </span>
          <span className="ml-auto flex items-center gap-1 text-[10px] text-[#B5AFA8]">
            <Clock className="w-3 h-3" />{timeAgo(article.published_at)}
          </span>
        </div>
        <a href={article.url} target="_blank" rel="noopener noreferrer">
          <h3 className="text-base font-bold text-[#2D2926] leading-snug group-hover:text-[#6B7E65] transition-colors line-clamp-3 mb-3">
            {article.title}
          </h3>
        </a>
        {article.summary && (
          <p className="text-xs text-[#6B645E] leading-relaxed line-clamp-3 mb-4">{article.summary}</p>
        )}
        <div className="flex items-center justify-between border-t border-[#F1EFE9] pt-3 mt-1">
          <a href={article.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-[10px] font-semibold text-[#8C9A86] hover:text-[#6B7E65] transition-colors">
            Habere git <ExternalLink className="w-3 h-3" />
          </a>
          <button
            onClick={() => setShowAiSummary(!showAiSummary)}
            className="flex items-center gap-1 text-[10px] font-bold text-[#8A5A36] bg-[#8A5A36]/10 px-2.5 py-0.5 rounded-full hover:bg-[#8A5A36]/20 transition-all select-none"
          >
            <span>✨ AI {isEn ? 'Summary' : 'Özeti'}</span>
            {showAiSummary ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
        {renderAiSummaryPanel()}
      </div>
    );
  }
  return (
    <div className="group py-3.5 border-b border-[#F1EFE9] last:border-0 hover:bg-[#F9F7F2] -mx-1 px-1 rounded-lg transition-colors">
      <div className="flex gap-3 items-start">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5"
          style={{ backgroundColor: accent }}>
          {sourceInitial(article.source)}
        </div>
        <div className="flex-1 min-w-0">
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            <p className="text-xs font-semibold text-[#2D2926] leading-snug line-clamp-2 group-hover:text-[#6B7E65] transition-colors">
              {article.title}
            </p>
          </a>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[9px] font-bold text-[#8C9A86] uppercase bg-[#8C9A86]/10 px-1.5 py-0.5 rounded-full">{article.ticker}</span>
            <span className="text-[9px] text-[#B5AFA8] truncate">{article.source}</span>
            <span className="text-[9px] text-[#B5AFA8] ml-auto shrink-0">{timeAgo(article.published_at)}</span>
            <button
              onClick={() => setShowAiSummary(!showAiSummary)}
              className="flex items-center gap-1 text-[9px] font-bold text-[#8A5A36] bg-[#8A5A36]/10 px-2 py-0.5 rounded-full hover:bg-[#8A5A36]/20 transition-all select-none"
            >
              <span>✨ AI</span>
              {showAiSummary ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>
        </div>
      </div>
      {renderAiSummaryPanel()}
    </div>
  );
}

function MacroCard({ item }: { item: MacroItem; key?: any }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex gap-3 items-start py-3 border-b border-[#F1EFE9] last:border-0 hover:bg-[#F9F7F2] -mx-1 px-1 rounded-lg transition-colors"
    >
      <TrendingUp className="w-3.5 h-3.5 text-[#8C9A86] shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-semibold text-[#2D2926] leading-snug line-clamp-2 group-hover:text-[#6B7E65] transition-colors">
          {item.title}
        </p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[9px] text-[#9E958C] truncate">{item.source}</span>
          {item.published_at && <span className="text-[9px] text-[#B5AFA8] ml-auto shrink-0">{timeAgo(item.published_at)}</span>}
        </div>
      </div>
    </a>
  );
}

type FilterTab = 'all' | 'portfolio' | 'macro';

// Modül-level cache: sayfa değişince sıfırlanmaz, component yeniden mount olunca anında gösterir
const _cache: {
  articles: NewsArticle[];
  macroItems: MacroItem[];
  fetchedAt: number;
  tickerKey: string;
} = { articles: [], macroItems: [], fetchedAt: 0, tickerKey: '' };
const STALE_MS = 15 * 60 * 1000; // 15 dakika

export default function NewsView({ holdings, settings }: NewsViewProps) {
  const isEn = settings.language === 'en';
  const tickers = [...new Set(holdings.filter(h => h.category !== 'Cash').map(h => h.symbol))];
  const tickerKey = tickers.join(',');
  const tefasTickers = tickers.filter(t => TEFAS_TICKERS.has(t.toUpperCase()));

  // Always keep a fresh ref so fetchAll never uses a stale closure
  const tickersRef = useRef<string[]>(tickers);
  tickersRef.current = tickers;

  // Cache'den başla — varsa anında göster, loading spinner yok
  const cacheHit = _cache.tickerKey === tickerKey && _cache.articles.length > 0;
  const [articles, setArticles] = useState<NewsArticle[]>(cacheHit ? _cache.articles : []);
  const [macroItems, setMacroItems] = useState<MacroItem[]>(cacheHit ? _cache.macroItems : []);
  const [loading, setLoading] = useState(!cacheHit && tickers.length > 0);
  const [lastUpdated, setLastUpdated] = useState(
    cacheHit ? new Date(_cache.fetchedAt).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : ''
  );
  const [filterTicker, setFilterTicker] = useState<string>('ALL');
  const [activeTab, setActiveTab] = useState<FilterTab>('all');

  // fetchAll reads tickers via ref — never a stale closure
  const fetchAll = useCallback(async (force = false) => {
    const curTickers = tickersRef.current;
    const curKey = curTickers.join(',');
    const now = Date.now();
    if (!force && _cache.tickerKey === curKey && curTickers.length > 0 && now - _cache.fetchedAt < STALE_MS) return;
    if (curTickers.length === 0) {
      // Only fetch macro feed when there are no portfolio tickers
      if (!force && _cache.fetchedAt > 0) return;
    }
    setLoading(curTickers.length > 0);
    try {
      const [newsData, feedData] = await Promise.allSettled([
        curTickers.length > 0 ? api.getNews(curTickers) : Promise.resolve({ articles: [] }),
        api.getNewsFeed(),
      ]);

      const newArticles = newsData.status === 'fulfilled' ? (newsData.value.articles || []) : _cache.articles;
      const newMacro = feedData.status === 'fulfilled' ? feedData.value.filter(i => i.tag === 'macro') : _cache.macroItems;

      _cache.articles = newArticles;
      _cache.macroItems = newMacro;
      _cache.fetchedAt = Date.now();
      _cache.tickerKey = curKey;

      setArticles(newArticles);
      setMacroItems(newMacro);
      setLastUpdated(new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }));
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch whenever tickerKey changes (holdings loaded or updated)
  useEffect(() => { fetchAll(); }, [tickerKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredArticles = filterTicker === 'ALL'
    ? articles
    : articles.filter(a => a.ticker === filterTicker);

  const featuredArticle = filteredArticles[0] || null;
  const listArticles = filteredArticles.slice(1);

  const tabs: { key: FilterTab; label: string; count?: number }[] = [
    { key: 'all', label: isEn ? 'All' : 'Tümü' },
    { key: 'portfolio', label: isEn ? 'Portfolio' : 'Portföy', count: articles.length },
    { key: 'macro', label: isEn ? 'Macro' : 'Makro', count: macroItems.length },
  ];

  return (
    <div className="space-y-5">

      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#2D2926]">
            {isEn ? 'News & Insights' : 'Haberler & Analiz'}
          </h1>
          <div className="flex items-center gap-2 mt-0.5">
            {lastUpdated && (
              <>
                <Wifi className="w-3 h-3 text-[#8C9A86]" />
                <span className="text-[10px] text-[#9E958C] font-medium">{lastUpdated}</span>
              </>
            )}
          </div>
        </div>
        <button
          onClick={() => fetchAll(true)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#8C9A86] text-white text-xs font-bold rounded-lg hover:bg-[#7a8874] transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          {isEn ? 'Refresh' : 'Yenile'}
        </button>
      </div>

      {tickers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <Newspaper className="w-12 h-12 text-[#D1CABF] mb-4" />
          <p className="text-[#9E958C] font-semibold text-sm">
            {isEn ? 'No holdings found.' : 'Portföyde varlık bulunamadı.'}
          </p>
        </div>
      ) : (
        <>
          {/* Tabs + Ticker Filters */}
          <div className="flex flex-col gap-3">
            <div className="flex gap-1 bg-[#F1EFE9] p-1 rounded-xl w-fit">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => { setActiveTab(tab.key); setFilterTicker('ALL'); }}
                  className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    activeTab === tab.key
                      ? 'bg-white text-[#2D2926] shadow-sm'
                      : 'text-[#9E958C] hover:text-[#6B645E]'
                  }`}
                >
                  {tab.label}
                  {tab.count != null && (
                    <span className={`ml-1.5 text-[9px] px-1.5 py-0.5 rounded-full ${
                      activeTab === tab.key ? 'bg-[#8C9A86]/15 text-[#8C9A86]' : 'bg-[#E8E2D9] text-[#9E958C]'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {activeTab !== 'macro' && (
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setFilterTicker('ALL')}
                  className={`px-3 py-1 rounded-full text-[10px] font-bold transition-colors ${
                    filterTicker === 'ALL' ? 'bg-[#2D2926] text-white' : 'bg-[#E8E2D9] text-[#6B645E] hover:bg-[#D1CABF]'
                  }`}
                >
                  {isEn ? 'All' : 'Tümü'}
                </button>
                {tickers.map(ticker => {
                  const count = articles.filter(a => a.ticker === ticker).length;
                  if (!count) return null;
                  return (
                    <button key={ticker} onClick={() => setFilterTicker(ticker)}
                      className={`px-3 py-1 rounded-full text-[10px] font-bold transition-colors ${
                        filterTicker === ticker ? 'bg-[#8C9A86] text-white' : 'bg-[#E8E2D9] text-[#6B645E] hover:bg-[#D1CABF]'
                      }`}
                    >
                      {ticker.replace('.IS', '')} <span className="opacity-60">{count}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Loading skeleton */}
          {loading && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              <div className="lg:col-span-2 space-y-4">
                <div className="bg-white border border-[#E8E2D9] rounded-2xl p-6 animate-pulse h-48">
                  <div className="w-24 h-4 bg-[#E8E2D9] rounded-full mb-4" />
                  <div className="space-y-2">
                    <div className="h-4 bg-[#E8E2D9] rounded w-full" />
                    <div className="h-4 bg-[#E8E2D9] rounded w-4/5" />
                    <div className="h-4 bg-[#E8E2D9] rounded w-3/5" />
                  </div>
                </div>
                {[1,2,3].map(i => (
                  <div key={i} className="flex gap-3 py-3 animate-pulse">
                    <div className="w-8 h-8 rounded-lg bg-[#E8E2D9] shrink-0" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 bg-[#E8E2D9] rounded w-full" />
                      <div className="h-3 bg-[#E8E2D9] rounded w-3/5" />
                    </div>
                  </div>
                ))}
              </div>
              <div className="space-y-3">
                {[1,2,3,4].map(i => <div key={i} className="h-14 bg-[#F1EFE9] rounded-xl animate-pulse" />)}
              </div>
            </div>
          )}

          {/* Main Layout */}
          {!loading && (
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab + filterTicker}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18 }}
              >
                {/* MACRO TAB */}
                {activeTab === 'macro' && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {macroItems.length === 0 ? (
                      <div className="col-span-2 py-16 text-center text-sm text-[#9E958C]">
                        {isEn ? 'No macro news available.' : 'Makro haber bulunamadı.'}
                      </div>
                    ) : macroItems.map((item, idx) => (
                      <motion.a
                        key={`macro-${idx}`}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className="group flex gap-4 bg-white border border-[#E8E2D9] rounded-xl p-4 hover:border-[#8C9A86] hover:shadow-sm transition-all"
                      >
                        <div className="w-9 h-9 rounded-xl bg-[#8C9A86]/10 flex items-center justify-center shrink-0">
                          <TrendingUp className="w-4 h-4 text-[#8C9A86]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-[#2D2926] leading-snug line-clamp-2 group-hover:text-[#6B7E65] transition-colors">
                            {item.title}
                          </p>
                          <div className="flex items-center gap-2 mt-1.5">
                            <span className="text-[9px] text-[#9E958C] truncate">{item.source}</span>
                            {item.published_at && <span className="text-[9px] text-[#B5AFA8] ml-auto shrink-0">{timeAgo(item.published_at)}</span>}
                          </div>
                        </div>
                      </motion.a>
                    ))}
                  </div>
                )}

                {/* PORTFOLIO / ALL TAB */}
                {activeTab !== 'macro' && (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                    {/* Left: Main feed */}
                    <div className="lg:col-span-2">
                      {filteredArticles.length === 0 ? (
                        <div className="py-16 text-center text-sm text-[#9E958C]">
                          {isEn ? 'No news found.' : 'Haber bulunamadı.'}
                        </div>
                      ) : (
                        <>
                          {/* Featured */}
                          {featuredArticle && (
                            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-4">
                              <ArticleCard article={featuredArticle} featured isEn={isEn} />
                            </motion.div>
                          )}

                          {/* List */}
                          <div className="bg-white border border-[#E8E2D9] rounded-2xl px-4 py-1">
                            {listArticles.map((article, idx) => (
                              <motion.div
                                key={`${article.url}-${idx}`}
                                initial={{ opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: idx * 0.025 }}
                              >
                                <ArticleCard article={article} isEn={isEn} />
                              </motion.div>
                            ))}
                          </div>
                        </>
                      )}
                    </div>

                    {/* Right: Sidebar */}
                    <div className="space-y-4">
                      {/* Macro sidebar */}
                      {macroItems.length > 0 && (
                        <div className="bg-white border border-[#E8E2D9] rounded-xl px-4 py-3">
                          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-[#F1EFE9]">
                            <TrendingUp className="w-3.5 h-3.5 text-[#8C9A86]" />
                            <span className="text-[10px] font-bold text-[#2D2926] uppercase tracking-wider">
                              {isEn ? 'Macro & Markets' : 'Makro & Piyasalar'}
                            </span>
                          </div>
                          {macroItems.slice(0, 8).map((item, idx) => (
                            <MacroCard key={idx} item={item} />
                          ))}
                        </div>
                      )}

                      {/* TEFAS fund cards */}
                      {tefasTickers.map(code => (
                        <FundMiniCard key={code} fundCode={code} isEn={isEn} />
                      ))}
                    </div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}
        </>
      )}
    </div>
  );
}
