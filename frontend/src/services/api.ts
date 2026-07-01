export const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

// Refresh token httpOnly cookie'de tutulur; access token kısa ömürlü olduğundan
// 401 alındığında burada sessizce yenilenir. Eşzamanlı 401'lerin tek bir refresh
// çağrısını paylaşması için in-flight promise'i modül seviyesinde tutuyoruz.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${BASE_URL}/api/users/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = await res.json();
        return data.access_token as string;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function logoutAndRedirect() {
  localStorage.removeItem('lucrum_auth_token');
  window.location.reload();
}

// Centralized request wrapper with auth header injection, cookie-based refresh, and 401 handling
async function request(url: string, options: RequestInit = {}, isRetry = false): Promise<any> {
  const token = localStorage.getItem('lucrum_auth_token');
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(url, { ...options, headers, credentials: 'include' });

  if (res.status === 401) {
    if (!isRetry) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        localStorage.setItem('lucrum_auth_token', newToken);
        return request(url, options, true);
      }
    }
    // Refresh de başarısız oldu -> gerçekten oturum sonlanmış
    logoutAndRedirect();
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

  async getUserProfile(): Promise<{ id: number; email: string; name: string; currency: string; subscription_tier: string; subscription_status: string; subscription_ends_at?: string; is_admin?: boolean }> {
    return request(`${BASE_URL}/api/users/me`);
  },

  async subscribeToPlan(plan: string): Promise<{ status: string; message: string; subscription_tier: string; subscription_status: string; subscription_ends_at: string }> {
    return request(`${BASE_URL}/api/users/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan })
    });
  },

  async logout(): Promise<void> {
    try {
      await fetch(`${BASE_URL}/api/users/logout`, { method: 'POST', credentials: 'include' });
    } finally {
      localStorage.removeItem('lucrum_auth_token');
    }
  },

  async tryRestoreSession(): Promise<string | null> {
    return refreshAccessToken();
  },

  async forgotPassword(email: string): Promise<{ status: string; message: string }> {
    return request(`${BASE_URL}/api/users/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
  },

  async resetPassword(token: string, newPassword: string): Promise<{ status: string; message: string }> {
    return request(`${BASE_URL}/api/users/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword })
    });
  },

  async verifyEmail(token: string): Promise<{ status: string; message: string }> {
    return request(`${BASE_URL}/api/users/verify-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });
  },

  async resendVerification(): Promise<{ status: string; message: string }> {
    return request(`${BASE_URL}/api/users/resend-verification`, { method: 'POST' });
  },

  async adminListUsers(page = 1, pageSize = 20, search = ''): Promise<{
    items: {
      id: number; email: string; name: string; subscription_tier: string; subscription_status: string;
      is_admin: boolean; is_active: boolean; email_verified: boolean; created_at: string;
    }[];
    total: number; page: number; page_size: number;
  }> {
    const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
    return request(`${BASE_URL}/api/admin/users?page=${page}&page_size=${pageSize}${searchParam}`);
  },

  async adminUpdateUser(userId: number, patch: { subscription_tier?: string; is_active?: boolean }): Promise<{
    id: number; email: string; name: string; subscription_tier: string; subscription_status: string;
    is_admin: boolean; is_active: boolean; email_verified: boolean; created_at: string;
  }> {
    return request(`${BASE_URL}/api/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  },

  async adminGetStats(): Promise<{
    total_users: number; active_users: number; verified_users: number; admin_users: number;
    tier_breakdown: Record<string, number>;
  }> {
    return request(`${BASE_URL}/api/admin/stats`);
  },
};
