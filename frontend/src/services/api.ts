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
  price_currency?: string;
  change_pct?: number | null;
  invested_tly?: number;
  invested_usd?: number | null;
  invested_eur?: number | null;
  invested_gbp?: number | null;
  current_value_tly?: number | null;
  current_value_usd?: number | null;
  current_value_eur?: number | null;
  current_value_gbp?: number | null;
}

export interface BackendLiability {
  id: number;
  name: string;
  liability_type: string;
  amount: number;
  currency: string;
  due_date?: string | null;
  interest_rate?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface PaymentHistoryItem {
  id: number;
  provider: string;
  plan_tier: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
}

export interface PortfolioResponse {
  timestamp: string;
  summary: {
    total_invested_tly: number;
    total_value_tly: number;
    total_return_tly: number;
    total_return_pct: number;
    total_invested_usd?: number;
    total_value_usd?: number;
    total_return_usd?: number;
    total_return_usd_pct?: number;
    total_invested_eur?: number;
    total_value_eur?: number;
    total_return_eur?: number;
    total_return_eur_pct?: number;
    total_invested_gbp?: number;
    total_value_gbp?: number;
    total_return_gbp?: number;
    total_return_gbp_pct?: number;
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
    // FastAPI hataları {"detail": "..."} JSON döner — parse edip temiz mesajı çıkar,
    // aksi halde kullanıcı ham JSON string görür (örn. pozisyon limiti hatası).
    let message = errText || `HTTP error! status: ${res.status}`;
    try {
      const parsed = JSON.parse(errText);
      if (typeof parsed?.detail === 'string') message = parsed.detail;
    } catch { /* JSON değil, ham metni kullan */ }
    throw new Error(message);
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

  async googleLogin(credential: string): Promise<{ access_token: string; token_type: string }> {
    return request(`${BASE_URL}/api/users/google-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential })
    });
  },

  async getExchangeRates(): Promise<ExchangeRateResponse> {
    return request(`${BASE_URL}/api/prices/rates`);
  },

  async getPortfolio(refresh = false): Promise<PortfolioResponse> {
    return request(`${BASE_URL}/api/portfolio?refresh=${refresh}`);
  },

  async getPerformance(days = 90, currency = 'TRY'): Promise<PerformanceResponse> {
    return request(`${BASE_URL}/api/portfolio/performance?days=${days}&currency=${currency}`);
  },

  async getLiabilities(): Promise<BackendLiability[]> {
    return request(`${BASE_URL}/api/liabilities`);
  },

  async addLiability(item: {
    name: string; liability_type: string; amount: number; currency: string;
    due_date?: string | null; interest_rate?: number | null;
  }): Promise<BackendLiability> {
    return request(`${BASE_URL}/api/liabilities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item)
    });
  },

  async updateLiability(id: number, item: {
    name?: string; liability_type?: string; amount?: number; currency?: string;
    due_date?: string | null; interest_rate?: number | null;
  }): Promise<BackendLiability> {
    return request(`${BASE_URL}/api/liabilities/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item)
    });
  },

  async deleteLiability(id: number): Promise<{ message: string }> {
    return request(`${BASE_URL}/api/liabilities/${id}`, {
      method: 'DELETE'
    });
  },

  async addPosition(pos: Omit<BackendPosition, 'id'>): Promise<BackendPosition> {
    return request(`${BASE_URL}/api/positions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pos)
    });
  },

  async deletePosition(id: number | string, sellPrice?: number): Promise<{ message: string }> {
    const qs = sellPrice != null ? `?sell_price=${sellPrice}` : '';
    return request(`${BASE_URL}/api/positions/${id}${qs}`, {
      method: 'DELETE'
    });
  },

  async updatePosition(id: number | string, update: {
    quantity?: number; buy_price?: number; delta_quantity?: number; delta_price?: number;
  }): Promise<BackendPosition> {
    return request(`${BASE_URL}/api/positions/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update)
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
    const raw: { date: string; price_usd: number | null; price_try: number | null }[] =
      await request(`${BASE_URL}/api/prices/history/${ticker}?days=${days}${classParam}`);
    // Backend price_usd/price_try döner, ancak korelasyon/benchmark hesaplamaları tek bir
    // 'price' alanı bekliyor — göreli fiyat hareketi için hangi para birimi tutarlı olsun
    // fark etmez, sadece bir tanesi seçilmeli.
    return raw
      .map((r) => ({ date: r.date, price: r.price_usd ?? r.price_try }))
      .filter((r): r is { date: string; price: number } => r.price != null);
  },

  async getNewsFeed(): Promise<{ ticker: string; tag: string; title: string; summary: string; url: string; source: string; published_at: string }[]> {
    return request(`${BASE_URL}/api/notifications/news`);
  },

  async getAssetOverview(ticker: string, assetClass: string): Promise<any> {
    return request(`${BASE_URL}/api/assets/${ticker}/overview?asset_class=${encodeURIComponent(assetClass)}`);
  },

  // Fiyat geçmişi + genel bilgiyi tek çağrıda getirir. Hem Mevcut Pozisyonlar'daki
  // varlık detay penceresi hem de Piyasalar sayfasındaki grafik/detay paneli AYNI
  // bu fonksiyonu kullanır — iki ayrı yerde birbirinden bağımsız fetch mantığı
  // olmadığından asset_class işleme farkı yüzünden aralarında sapma oluşamaz.
  async getAssetDetail(ticker: string, assetClass: string, days = 90): Promise<{
    history: { date: string; price: number }[];
    overview: any;
  }> {
    const [history, overview] = await Promise.all([
      this.getPriceHistory(ticker, days, assetClass),
      this.getAssetOverview(ticker, assetClass),
    ]);
    return { history, overview };
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

  async subscribeToPlan(plan: string): Promise<{ status: string; message: string; subscription_tier: string; subscription_status: string; subscription_ends_at: string | null }> {
    return request(`${BASE_URL}/api/users/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan })
    });
  },

  async createLemonSqueezyCheckout(plan: string): Promise<{ checkout_url: string }> {
    return request(`${BASE_URL}/api/payments/lemonsqueezy/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan })
    });
  },

  async getPaymentHistory(): Promise<{
    id: number; provider: string; plan_tier: string; amount: number; currency: string; status: string; created_at: string;
  }[]> {
    return request(`${BASE_URL}/api/payments/history`);
  },

  async logout(): Promise<void> {
    try {
      await fetch(`${BASE_URL}/api/users/logout`, { method: 'POST', credentials: 'include' });
    } finally {
      localStorage.removeItem('lucrum_auth_token');
    }
  },

  async deleteAccount(): Promise<void> {
    try {
      await request(`${BASE_URL}/api/users/me`, { method: 'DELETE' });
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

  async adminGetAuditLog(page = 1, pageSize = 20): Promise<{
    items: {
      id: number; admin_user_id: number | null; admin_email: string | null;
      target_user_id: number | null; target_email: string | null;
      action: string; details: string | null; created_at: string;
    }[];
    total: number; page: number; page_size: number;
  }> {
    return request(`${BASE_URL}/api/admin/audit-log?page=${page}&page_size=${pageSize}`);
  },

  async adminGetUserPortfolio(userId: number): Promise<any> {
    return request(`${BASE_URL}/api/admin/users/${userId}/portfolio`);
  },
};
