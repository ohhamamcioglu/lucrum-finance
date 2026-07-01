export const BASE_URL = 'http://localhost:8000';

export interface BackendPosition {
  id: number;
  ticker: string;
  asset_class: string;
  quantity: number;
  buy_price: number;
  buy_date: string;
  buy_currency: string;
  current_price?: number;
  invested_tly?: number;
  current_value_tly?: number;
}

export interface PortfolioResponse {
  timestamp: string;
  summary: {
    total_invested_tly: number;
    total_value_tly: number;
    total_return_tly: number;
    total_return_pct: number;
    by_asset_class: Record<string, {
      count: number;
      invested_tly: number;
      current_value_tly: number;
      return_tly: number;
      return_pct: number;
    }>;
  };
  holdings: BackendPosition[];
}

export interface ExchangeRateResponse {
  rate: number;
  usd_rate: number;
  eur_rate: number;
  gbp_rate?: number;
  timestamp: string;
}

export interface PerformanceHistoryPoint {
  date: string;
  portfolio: number;
  bist100: number;
  sp500: number;
  btc: number;
  value: number;
  invested: number;
}

export interface PerformanceResponse {
  twrr: number;
  volatility: number;
  max_drawdown: number;
  history: PerformanceHistoryPoint[];
}

// Centralized request wrapper with auth header injection and 401 handling
async function request(url: string, options: RequestInit = {}): Promise<any> {
  const token = localStorage.getItem('lucrum_auth_token');
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  const res = await fetch(url, { ...options, headers });
  
  if (res.status === 401) {
    // Access token expired or invalid -> log out
    localStorage.removeItem('lucrum_auth_token');
    // Clear and reload page to trigger redirect to login view
    window.location.reload();
    throw new Error('Unauthorized');
  }
  
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Request failed');
    throw new Error(errText || `HTTP error! status: ${res.status}`);
  }
  
  return res.json();
}

export const api = {
  async register(email: string, name: string, password: string): Promise<{ access_token: string; token_type: string }> {
    return request(`${BASE_URL}/api/users/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, name, password })
    });
  },

  async login(email: string, password: string): Promise<{ access_token: string; token_type: string }> {
    return request(`${BASE_URL}/api/users/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
  },

  async getExchangeRates(): Promise<ExchangeRateResponse> {
    return request(`${BASE_URL}/api/exchange-rate`);
  },

  async getPortfolio(refresh = false): Promise<PortfolioResponse> {
    return request(`${BASE_URL}/api/portfolio?refresh=${refresh}`);
  },

  async getPerformance(days = 90, currency = 'TRY'): Promise<PerformanceResponse> {
    return request(`${BASE_URL}/api/portfolio/performance?days=${days}&currency=${currency}`);
  },

  async addPosition(pos: Omit<BackendPosition, 'id'>): Promise<BackendPosition> {
    return request(`${BASE_URL}/api/positions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pos)
    });
  },

  async deletePosition(id: number | string): Promise<{ message: string }> {
    return request(`${BASE_URL}/api/positions/${id}`, {
      method: 'DELETE'
    });
  },

  async resetPortfolio(): Promise<{ status: string; message: string }> {
    return request(`${BASE_URL}/api/portfolio/reset`, {
      method: 'POST'
    });
  },

  async getNews(tickers?: string[]): Promise<{ generated_at: string; tickers: string[]; articles: import('../types').NewsArticle[] }> {
    const params = tickers && tickers.length > 0 ? `?tickers=${tickers.join(',')}` : '';
    return request(`${BASE_URL}/api/news${params}`);
  },

  async getFundDisclosures(fundCode: string, days = 180): Promise<{
    fund_code: string;
    fund_name: string;
    kap_page: string;
    pys_oid_found: boolean;
    disclosures: { index: number; title: string; subject: string; publish_date: string; year: number; url: string }[];
    note: string;
  }> {
    return request(`${BASE_URL}/api/funds/${fundCode}/disclosures?days=${days}`);
  },

  async getFundBreakdown(fundCode: string): Promise<{
    fund_code: string;
    fund_name: string;
    date: string;
    price: number | null;
    portfolio_size: number | null;
    investor_count: number | null;
    allocation: { label: string; pct: number }[];
  }> {
    return request(`${BASE_URL}/api/funds/${fundCode}/breakdown`);
  },

  async getPriceHistory(ticker: string, days = 90, assetClass?: string): Promise<{ date: string; price: number }[]> {
    const classParam = assetClass ? `&asset_class=${encodeURIComponent(assetClass)}` : '';
    return request(`${BASE_URL}/api/prices/${ticker}/history?days=${days}${classParam}`);
  },

  async getNewsFeed(): Promise<{ ticker: string; tag: string; title: string; summary: string; url: string; source: string; published_at: string }[]> {
    return request(`${BASE_URL}/api/notifications/news-feed`);
  },

  async getAssetOverview(ticker: string, assetClass: string): Promise<any> {
    return request(`${BASE_URL}/api/assets/${ticker}/overview?asset_class=${encodeURIComponent(assetClass)}`);
  },

  async getAssetFundamentals(ticker: string, assetClass: string): Promise<any> {
    return request(`${BASE_URL}/api/assets/${ticker}/fundamentals?asset_class=${encodeURIComponent(assetClass)}`);
  },

  async getAssetIndicators(ticker: string, assetClass: string, interval = '1day', periods = 60): Promise<any> {
    return request(`${BASE_URL}/api/assets/${ticker}/indicators?asset_class=${encodeURIComponent(assetClass)}&interval=${interval}&periods=${periods}`);
  },

  async searchAssets(query: string): Promise<{
    symbol: string; name: string; category: string; asset_class: string; sector: string; riskScore: number;
  }[]> {
    if (!query || query.length < 1) return [];
    return request(`${BASE_URL}/api/assets/search?query=${encodeURIComponent(query)}`);
  },

  async getRiskScores(): Promise<Record<string, number>> {
    const data = await request(`${BASE_URL}/api/portfolio/risk-scores`);
    return data.scores ?? {};
  },

  async getUserProfile(): Promise<{ id: number; email: string; name: string; currency: string; subscription_tier: string; subscription_status: string; subscription_ends_at?: string }> {
    return request(`${BASE_URL}/api/users/me`);
  },

  async subscribeToPlan(plan: string): Promise<{ status: string; message: string; subscription_tier: string; subscription_status: string; subscription_ends_at: string }> {
    return request(`${BASE_URL}/api/users/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan })
    });
  },
};
