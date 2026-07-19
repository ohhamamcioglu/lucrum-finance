export type AssetCategory = 'Equity' | 'Crypto' | 'FixedIncome' | 'Cash';

export interface Holding {
  id: string;
  symbol: string;
  name: string;
  category: AssetCategory;
  sector: string;
  shares: number;
  avgBuyPrice: number;
  currentPrice: number;
  riskScore: number; // 1-10
  assetClass?: string;
  changePct?: number | null; // günlük değişim yüzdesi (ör. 2.34 = +%2.34), veri yoksa null
  buyDate?: string; // YYYY-MM-DD — alım tarihi, kur/kâr-zarar hesabı için backend'e gönderilir
  priceEffectPct?: number | null; // yabancı para pozisyonda getirinin varlık fiyatından gelen kısmı
  fxEffectPct?: number | null; // yabancı para pozisyonda getirinin kur hareketinden gelen kısmı — TRY pozisyonda hep 0
  taxWrapper?: string | null; // UK vergi sarmalı (GIA/ISA/SIPP) — sadece UK vergi hesaplayıcısı için anlamlı
}

export interface Transaction {
  id: string;
  symbol: string;
  name: string;
  type: 'BUY' | 'SELL';
  shares: number;
  price: number;
  date: string;
  category: AssetCategory;
}

export interface UserSettings {
  baseCurrency: 'USD' | 'EUR' | 'TRY' | 'GBP';
  benchmark: 'S&P 500' | 'Nasdaq' | 'Bitcoin' | 'Gold' | 'BIST100' | 'DAX' | 'FTSE 100' | 'CAC 40' | 'Euro Stoxx';
  riskTolerance: 'Conservative' | 'Balanced' | 'Aggressive';
  userName: string;
  userRole: string;
  userAvatar: string;
  language: 'tr' | 'en';
}

export type ActiveTab = 'portfolio' | 'analytics' | 'risk' | 'markets' | 'news' | 'liabilities' | 'tax' | 'settings';

export type LiabilityType = 'Loan' | 'CreditCard' | 'Mortgage' | 'Other';

export interface Liability {
  id: number;
  name: string;
  liability_type: LiabilityType;
  amount: number;
  currency: 'TRY' | 'USD' | 'EUR' | 'GBP';
  due_date?: string | null;
  interest_rate?: number | null;
}

export interface NewsArticle {
  ticker: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  published_at: string;
}

export interface MarketAsset {
  symbol: string;
  name: string;
  category: AssetCategory;
  sector: string;
  price: number;
  change24h: number;
  volume24h: string;
  marketCap: string;
  peRatio?: number;
  beta: number;
  sparkline: number[];
  description: string;
  // Backend'in tanıdığı tam asset_class (ör. "TEFAS Fonu", "BIST Hissesi").
  // Eskiden description string'ine " · assetClass" olarak gömülüyordu — asset
  // overview yüklendiğinde description backend'in düz metniyle üzerine
  // yazılınca bu kodlama bozuluyor ve yanlış varlık sınıfı tahmin ediliyordu
  // (ör. TEFAS fonu "FixedIncome" sanılıp Twelve Data'da alakasız bir
  // sembolün fiyatı gösteriliyordu). Artık ayrı, asla üzerine yazılmayan bir
  // alan.
  assetClass?: string;
}
