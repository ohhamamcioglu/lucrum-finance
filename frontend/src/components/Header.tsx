import { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Bell, Newspaper, TrendingUp, Loader2, Menu } from 'lucide-react';
import { UserSettings } from '../types';
import { formatCurrency, convertCurrency } from '../utils';
import { useT } from '../i18n';
import { api } from '../services/api';

interface NewsItem {
  ticker: string;
  tag: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  published_at: string;
}

interface HeaderProps {
  onSearchSelectAsset: (symbol: string, assetClass: string) => void;
  settings: UserSettings;
  exchangeRates: { usd_rate: number; eur_rate: number };
  onMenuClick: () => void;
}

const SEEN_KEY = 'lucrum_seen_news_urls';
const POLL_INTERVAL = 15 * 60 * 1000; // 15 dakika

function getSeenUrls(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}

function saveSeenUrls(urls: Set<string>) {
  try {
    // En fazla 500 URL tut
    const arr = [...urls].slice(-500);
    localStorage.setItem(SEEN_KEY, JSON.stringify(arr));
  } catch { /* ignore */ }
}

function formatRelativeTime(published: string): string {
  if (!published) return '';
  try {
    const date = new Date(published);
    if (isNaN(date.getTime())) return published;
    const diff = Date.now() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Az önce';
    if (mins < 60) return `${mins}d önce`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}s önce`;
    const days = Math.floor(hrs / 24);
    return `${days}g önce`;
  } catch { return ''; }
}

interface SearchResult {
  symbol: string; name: string; category: string; asset_class: string; sector: string; riskScore: number;
}

export default function Header({ onSearchSelectAsset, settings, exchangeRates, onMenuClick }: HeaderProps) {
  const t = useT(settings.language);
  const [searchQuery, setSearchQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [newsFeed, setNewsFeed] = useState<NewsItem[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced dynamic search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    setSearchLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await api.searchAssets(searchQuery.trim());
        setSearchResults(results);
      } catch { setSearchResults([]); }
      finally { setSearchLoading(false); }
    }, 250);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery]);

  const fetchFeed = useCallback(async () => {
    setFeedLoading(true);
    try {
      const items = await api.getNewsFeed();
      setNewsFeed(items);
      const seen = getSeenUrls();
      const unread = items.filter(i => i.url && !seen.has(i.url)).length;
      setUnreadCount(unread);
    } catch { /* silent */ }
    finally { setFeedLoading(false); }
  }, []);

  useEffect(() => {
    fetchFeed();
    const interval = setInterval(fetchFeed, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchFeed]);

  const markAllRead = () => {
    const seen = getSeenUrls();
    newsFeed.forEach(i => { if (i.url) seen.add(i.url); });
    saveSeenUrls(seen);
    setUnreadCount(0);
  };

  const handleOpenPanel = () => {
    setShowNotifications(v => !v);
  };

  // Panel açılınca okundu işaretle
  useEffect(() => {
    if (showNotifications && newsFeed.length > 0) {
      markAllRead();
    }
  }, [showNotifications]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="fixed top-0 right-0 left-0 md:left-64 h-16 bg-[#F9F7F2] border-b border-[#E8E2D9] z-40 select-none">
      <div className="flex justify-between items-center gap-3 px-4 md:px-8 h-full">

        {/* Hamburger — sadece mobilde görünür, Sidebar'ı off-canvas açar */}
        <button
          type="button"
          onClick={onMenuClick}
          className="md:hidden shrink-0 p-1.5 -ml-1.5 text-[#4A443F] hover:text-[#8C9A86] rounded hover:bg-[#F1EFE9]"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Search */}
        <div ref={searchRef} className="relative flex-1 min-w-0 md:w-96 md:flex-none">
          <div className="relative w-full rounded">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#9E958C] w-4 h-4" />
            <input
              id="header-search-input"
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setShowResults(true); }}
              onFocus={() => setShowResults(true)}
              placeholder={t.searchPlaceholder}
              className="w-full bg-[#F1EFE9] border border-[#E8E2D9] text-sm text-[#4A443F] rounded-md py-1.5 pl-10 pr-4 placeholder-[#9E958C]/65 focus:outline-none focus:border-[#8C9A86] focus:ring-1 focus:ring-[#8C9A86] transition-all"
            />
          </div>

          {showResults && searchQuery && (
            <div className="absolute top-12 left-0 right-0 bg-white border border-[#E8E2D9] rounded-lg shadow-xl overflow-hidden max-h-80 overflow-y-auto custom-scrollbar z-50">
              <div className="px-3.5 py-2 text-[10px] uppercase tracking-wider font-bold text-[#9E958C] border-b border-[#E8E2D9] flex items-center justify-between">
                <span>{t.matchingInstruments}</span>
                {searchLoading && <Loader2 className="w-3 h-3 animate-spin text-[#8C9A86]" />}
              </div>
              {searchResults.length > 0 ? (
                searchResults.map((asset) => (
                  <button
                    key={`${asset.symbol}-${asset.asset_class}`}
                    id={`search-result-${asset.symbol}-${asset.asset_class.replace(/[^A-Za-z0-9]/g, '')}`}
                    onClick={() => { onSearchSelectAsset(asset.symbol, asset.asset_class); setSearchQuery(''); setShowResults(false); setSearchResults([]); }}
                    className="w-full text-left px-4 py-2.5 hover:bg-[#F1EFE9] transition-colors flex justify-between items-center border-b border-[#E8E2D9]/40 last:border-b-0"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded bg-[#8C9A86]/10 flex items-center justify-center font-mono text-xs font-bold text-[#8C9A86]">
                        {asset.symbol.substring(0, 2)}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-[#2D2926]">{asset.symbol}</div>
                        <div className="text-[11px] text-[#6B645E] font-semibold">{asset.name}</div>
                      </div>
                    </div>
                    <span className="text-[9px] font-bold text-[#9E958C] bg-[#F1EFE9] px-2 py-0.5 rounded-full uppercase">
                      {asset.asset_class}
                    </span>
                  </button>
                ))
              ) : !searchLoading ? (
                <div className="p-4 text-center text-xs text-[#9E958C]/75">{t.noMatchesFound}</div>
              ) : null}
            </div>
          )}
        </div>

        {/* Right */}
        <div className="flex items-center gap-3 md:gap-6 shrink-0">
          <div className="flex items-center gap-4 relative">

            {/* Notification Bell */}
            <div ref={notifRef} className="relative">
              <button
                id="notification-bell-btn"
                onClick={handleOpenPanel}
                className="text-[#6B645E] hover:text-[#8C9A86] transition-colors p-1.5 rounded hover:bg-[#F1EFE9] relative"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 bg-[#B5836F] rounded-full ring-2 ring-[#F9F7F2] flex items-center justify-center">
                    <span className="text-[9px] font-bold text-white px-0.5">{unreadCount > 9 ? '9+' : unreadCount}</span>
                  </span>
                )}
              </button>

              {/* Notifications Panel */}
              {showNotifications && (
                <div className="absolute top-10 right-0 w-[calc(100vw-2rem)] max-w-96 bg-white border border-[#E8E2D9] rounded-xl shadow-2xl z-50 overflow-hidden">
                  {/* Header */}
                  <div className="px-4 py-3 border-b border-[#E8E2D9] flex justify-between items-center bg-[#F9F7F2]">
                    <div className="flex items-center gap-2">
                      <Newspaper className="w-3.5 h-3.5 text-[#8C9A86]" />
                      <span className="text-xs font-bold text-[#2D2926] uppercase tracking-wider">
                        Haberler & Bildirimler
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      {feedLoading && <Loader2 className="w-3 h-3 animate-spin text-[#9E958C]" />}
                      <button
                        onClick={fetchFeed}
                        className="text-[10px] text-[#8C9A86] hover:text-[#7A8874] font-bold"
                      >
                        Yenile
                      </button>
                    </div>
                  </div>

                  {/* Feed */}
                  <div className="divide-y divide-[#E8E2D9]/40 max-h-[420px] overflow-y-auto custom-scrollbar">
                    {feedLoading && newsFeed.length === 0 ? (
                      <div className="py-10 text-center text-xs text-[#9E958C] flex flex-col items-center gap-2">
                        <Loader2 className="w-5 h-5 animate-spin text-[#8C9A86]" />
                        <span>Haberler yükleniyor…</span>
                      </div>
                    ) : newsFeed.length === 0 ? (
                      <div className="py-10 text-center text-xs text-[#9E958C]">
                        Henüz haber yok
                      </div>
                    ) : (
                      newsFeed.map((item, idx) => (
                        <a
                          key={`${item.url}-${idx}`}
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block px-4 py-3 hover:bg-[#F1EFE9] transition-colors group"
                        >
                          <div className="flex gap-2.5 items-start">
                            <div className="shrink-0 mt-0.5">
                              {item.tag === 'macro' ? (
                                <TrendingUp className="w-3.5 h-3.5 text-[#8C9A86]" />
                              ) : (
                                <div className="w-5 h-5 rounded bg-[#8C9A86]/15 flex items-center justify-center font-mono text-[8px] font-bold text-[#8C9A86]">
                                  {(item.tag || item.ticker || '?').replace('.IS', '').substring(0, 3)}
                                </div>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-[11px] font-semibold text-[#2D2926] leading-snug line-clamp-2 group-hover:text-[#8C9A86] transition-colors">
                                {item.title}
                              </p>
                              <div className="flex items-center gap-2 mt-1">
                                <span className="text-[9px] text-[#9E958C] font-medium truncate max-w-[140px]">{item.source}</span>
                                {item.tag !== 'macro' && (
                                  <>
                                    <span className="text-[#E8E2D9]">·</span>
                                    <span className="text-[9px] font-bold text-[#8C9A86] uppercase">{item.tag.replace('.IS', '')}</span>
                                  </>
                                )}
                                {item.published_at && (
                                  <>
                                    <span className="text-[#E8E2D9]">·</span>
                                    <span className="text-[9px] text-[#9E958C]">{formatRelativeTime(item.published_at)}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        </a>
                      ))
                    )}
                  </div>

                  {/* Footer */}
                  {newsFeed.length > 0 && (
                    <div className="px-4 py-2 border-t border-[#E8E2D9] bg-[#F9F7F2] text-center">
                      <span className="text-[10px] text-[#9E958C] font-medium">
                        {t.newsFeedFooter(newsFeed.length)}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>

          </div>

          {/* Dar ekranlarda tekrar eden marka yazısı yer kaplamasın diye gizleniyor
              (zaten hamburger menüsü açıldığında Sidebar'da görünüyor). */}
          <div className="hidden md:block h-5 w-[1px] bg-[#E8E2D9]"></div>

          <div className="hidden md:block text-[#8C9A86] font-serif font-bold text-sm tracking-wide">
            LUCRUM
          </div>
        </div>
      </div>
    </header>
  );
}
