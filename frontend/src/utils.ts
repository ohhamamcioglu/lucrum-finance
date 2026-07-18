import { Holding, MarketAsset, AssetCategory, UserSettings } from './types';

export const MARKET_ASSETS: MarketAsset[] = [
  {
    symbol: 'NVDA',
    name: 'Nvidia Corp',
    category: 'Equity',
    sector: 'Technology',
    price: 135.0,
    change24h: 3.42,
    volume24h: '42.1B',
    marketCap: '3.32T',
    peRatio: 68.4,
    beta: 1.85,
    sparkline: [128, 129, 131, 130, 132, 133, 135],
    description: 'NVIDIA Corporation designs graphics processing units for the gaming and professional markets, as well as system on a chip units for the mobile computing and automotive market. It is a leading force in AI accelerators.',
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'BTC',
    name: 'Bitcoin',
    category: 'Crypto',
    sector: 'Cryptocurrency',
    price: 65000.0,
    change24h: 1.85,
    volume24h: '28.5B',
    marketCap: '1.28T',
    beta: 2.1,
    sparkline: [62000, 61500, 63000, 64200, 63500, 64800, 65000],
    description: 'Bitcoin is a decentralized digital currency, without a central bank or single administrator, that can be sent from user to user on the peer-to-peer bitcoin network without the need for intermediaries.',
    assetClass: 'Kripto'
  },
  {
    symbol: 'GS',
    name: 'Goldman Sachs Group Inc',
    category: 'Equity',
    sector: 'Financials',
    price: 460.0,
    change24h: -0.75,
    volume24h: '1.8B',
    marketCap: '148.5B',
    peRatio: 15.2,
    beta: 1.15,
    sparkline: [468, 465, 467, 462, 463, 461, 460],
    description: 'The Goldman Sachs Group, Inc. is a leading global investment banking, securities and investment management firm that provides a wide range of financial services to a substantial and diversified client base.',
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'MSFT',
    name: 'Microsoft Corp',
    category: 'Equity',
    sector: 'Technology',
    price: 420.0,
    change24h: 0.54,
    volume24h: '18.9B',
    marketCap: '3.12T',
    peRatio: 35.8,
    beta: 0.89,
    sparkline: [415, 417, 416, 418, 422, 419, 420],
    description: 'Microsoft Corporation is an American multinational technology corporation headquarterd in Redmond, Washington. It develops, licenses, and supports software, consumer electronics, personal computers, and services.',
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'AAPL',
    name: 'Apple Inc',
    category: 'Equity',
    sector: 'Technology',
    price: 220.0,
    change24h: 1.12,
    volume24h: '22.4B',
    marketCap: '3.38T',
    peRatio: 31.2,
    beta: 1.02,
    sparkline: [214, 216, 215, 218, 221, 219, 220],
    description: 'Apple Inc. is an American multinational technology company headquartered in Cupertino, California. It designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories.',
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'ETH',
    name: 'Ethereum',
    category: 'Crypto',
    sector: 'Cryptocurrency',
    price: 3450.0,
    change24h: 2.15,
    volume24h: '14.2B',
    marketCap: '414.2B',
    beta: 1.95,
    sparkline: [3300, 3280, 3350, 3420, 3380, 3430, 3450],
    description: 'Ethereum is a decentralized, open-source blockchain with smart contract functionality. Ether is the native cryptocurrency of the platform, second only to Bitcoin in market capitalization.',
    assetClass: 'Kripto'
  },
  {
    symbol: 'US10Y',
    name: 'US 10-Year Treasury',
    category: 'FixedIncome',
    sector: 'Government',
    price: 100.0,
    change24h: 0.05,
    volume24h: '85.0B',
    marketCap: 'N/A',
    beta: 0.1,
    sparkline: [99.8, 99.9, 100.0, 99.95, 100.02, 100.05, 100.0],
    description: 'The United States 10-Year Treasury Note is a debt obligation issued by the United States government that matures in 10 years. It serves as an essential global financial benchmark.',
    // Not: category 'FixedIncome' portföy tahsis grubu için, ama bu TEFAS fonu
    // DEĞİL — sentetik bir gösterge sembolü. assetClass'ı 'ABD Hisse/ETF' olarak
    // sabitlemek zorunlu, aksi halde getAssetClass kategoriden TEFAS Fonu tahmin
    // edip backend'i gerçek olmayan bir TEFAS koduna sorguluyordu.
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'TSLA',
    name: 'Tesla Inc',
    category: 'Equity',
    sector: 'Technology',
    price: 185.0,
    change24h: -2.34,
    volume24h: '12.8B',
    marketCap: '589.4B',
    peRatio: 54.2,
    beta: 2.24,
    sparkline: [195, 192, 189, 186, 188, 184, 185],
    description: 'Tesla, Inc. designs, develops, manufactures, sells, and leases fully electric vehicles, energy generation and storage systems, and offers services related to its products.',
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'GLD',
    name: 'SPDR Gold Shares',
    category: 'FixedIncome',
    sector: 'Commodities',
    price: 215.0,
    change24h: 0.42,
    volume24h: '2.5B',
    marketCap: '62.4B',
    beta: 0.25,
    sparkline: [212, 213, 214, 213.5, 214.8, 215.2, 215.0],
    description: 'SPDR Gold Shares is an investment fund incorporated in the USA. The objective of the Trust is for the Shares to reflect the performance of the price of gold bullion.',
    // GLD, TEFAS fonu değil — ABD'de (NYSE Arca) işlem gören gerçek bir ETF.
    // category 'FixedIncome' sadece portföy tahsis grubu içindir, bkz. US10Y notu.
    assetClass: 'ABD Hisse/ETF'
  },
  {
    symbol: 'JPM',
    name: 'JPMorgan Chase & Co',
    category: 'Equity',
    sector: 'Financials',
    price: 198.0,
    change24h: 0.85,
    volume24h: '3.1B',
    marketCap: '568.2B',
    peRatio: 12.1,
    beta: 1.05,
    sparkline: [194, 195, 197, 196, 198, 197.5, 198.0],
    description: 'JPMorgan Chase & Co. is an American multinational finance corporation. It is the largest bank in the United States and the worlds largest bank by market capitalization.',
    assetClass: 'ABD Hisse/ETF'
  }
];

export const INITIAL_SETTINGS: UserSettings = {
  baseCurrency: 'USD',
  benchmark: 'S&P 500',
  riskTolerance: 'Balanced',
  userName: 'Investigator Profile',
  userRole: 'Admin Tier',
  userAvatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAZinbteFiV_JgbP2U0pkthU4cqzbqAIX6KdJUpnlblhx9NgaNTgwrLNEcns5S6zf7wcd3XXbdklFELrTvLcYxDOHkJf8lUJ4-15eMr-Wd_qwLk_ZfjIm_P1BKvXYmL9wY5wkgEHpvlDb9M_JG9KmpM96O5NZvV5ilbA6HcEss6F9TYFKANVeGKPfGuB_MbwbW5odUhVlhW_SQJRcCMiYU5aEny1wWF7LqaODAtbfBO9MZDs9Bhb1_UkUPgG5H6OTDF1GuRPSUTJbWz',
  language: 'tr',
};

export const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  TRY: '₺',
  GBP: '£'
};

export function formatCurrency(value: number, currency: string = 'USD'): string {
  const symbol = CURRENCY_SYMBOLS[currency] || '$';
  return symbol + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function convertCurrency(
  value: number,
  from: string,
  to: string,
  rates: { usd_rate: number; eur_rate: number; gbp_rate?: number }
): number {
  if (!value) return 0;
  if (from === to) return value;
  
  const getRate = (currency: string): number => {
    if (currency === 'USD') return rates.usd_rate;
    if (currency === 'EUR') return rates.eur_rate;
    if (currency === 'GBP') return rates.gbp_rate ?? rates.usd_rate * 1.27;
    return 1.0; // TRY
  };

  const valueInTry = value * getRate(from);
  return valueInTry / getRate(to);
}

export function calculatePortfolio(holdings: Holding[]) {
  let totalValue = 0;
  let totalCost = 0;
  let weightedRisk = 0;
  
  const holdingValues = holdings.map(h => {
    const value = h.shares * h.currentPrice;
    const cost = h.shares * h.avgBuyPrice;
    totalValue += value;
    totalCost += cost;
    weightedRisk += value * h.riskScore;
    return {
      ...h,
      value,
      cost,
      unrealizedPL: value - cost,
      unrealizedPLPercent: cost > 0 ? ((value - cost) / cost) * 100 : 0
    };
  });

  const portfolioRiskScore = totalValue > 0 ? weightedRisk / totalValue : 0;
  const unrealizedPL = totalValue - totalCost;
  const unrealizedPLPercent = totalCost > 0 ? (unrealizedPL / totalCost) * 100 : 0;

  // Group allocations
  const categoryValues: Record<AssetCategory, number> = {
    Equity: 0,
    Crypto: 0,
    FixedIncome: 0,
    Cash: 0
  };

  const detailedValues: Record<string, number> = {
    BIST_STOCK: 0,
    TEFAS_FUND: 0,
    US_STOCK: 0,
    US_ETF: 0,
    CRYPTO: 0,
    COMMODITY: 0,
    CASH: 0,
    OTHER: 0
  };

  holdingValues.forEach(h => {
    categoryValues[h.category] += h.value;

    let detKey = 'OTHER';
    const ac = h.assetClass || '';
    const sym = h.symbol.toUpperCase();
    
    if (ac === 'BIST Hissesi' || sym.endsWith('.IS')) {
      detKey = 'BIST_STOCK';
    } else if (ac === 'TEFAS Fonu') {
      detKey = 'TEFAS_FUND';
    } else if (ac === 'Kripto' || h.category === 'Crypto') {
      detKey = 'CRYPTO';
    } else if (ac === 'Nakit' || h.category === 'Cash' || ac === 'Cash') {
      detKey = 'CASH';
    } else if (ac === 'Emtia') {
      detKey = 'COMMODITY';
    } else if (ac === 'ABD Hisse/ETF' || h.category === 'Equity') {
      const isEtf = [
        'VOO', 'QQQ', 'SPY', 'VTI', 'VEA', 'VNQ', 'GLD', 'TLT', 'URNM', 'SMH',
        'XLK', 'XLF', 'XLV', 'XLE', 'XLY', 'XLI', 'XLP', 'XLB', 'XLU', 'XLC',
        'IWM', 'EEM', 'VWO', 'IVV', 'AGG', 'BND', 'LQD', 'HYG', 'DIA', 'GDX'
      ].includes(sym);
      detKey = isEtf ? 'US_ETF' : 'US_STOCK';
    }
    detailedValues[detKey] += h.value;
  });

  const categoryAllocations = Object.entries(categoryValues).map(([key, val]) => {
    return {
      category: key as AssetCategory,
      value: val,
      percent: totalValue > 0 ? (val / totalValue) * 100 : 0
    };
  });

  const detailedAllocations = Object.entries(detailedValues)
    .map(([key, val]) => ({
      category: key,
      value: val,
      percent: totalValue > 0 ? (val / totalValue) * 100 : 0
    }))
    .filter(a => a.value > 0)
    .sort((a, b) => b.value - a.value);

  const holdingsWithAllocation = holdingValues.map(h => ({
    ...h,
    allocationPercent: totalValue > 0 ? (h.value / totalValue) * 100 : 0
  })).sort((a, b) => b.value - a.value);

  return {
    totalValue,
    totalCost,
    unrealizedPL,
    unrealizedPLPercent,
    portfolioRiskScore,
    categoryAllocations,
    detailedAllocations,
    holdings: holdingsWithAllocation,
    cashAmount: categoryValues.Cash
  };
}

// stress testing scenarios definition
export interface StressScenario {
  name: string;
  description: string;
  impactEquity: number; // Percent change e.g. -30 for 30% drop
  impactCrypto: number;
  impactFixedIncome: number;
  impactCash: number;
}

export const STRESS_SCENARIOS: StressScenario[] = [
  {
    name: '2008 Financial Crisis Recurrence',
    description: 'Severe systemic banking collapse. High equity selloff, bonds rally slightly, crypto crashes heavily.',
    impactEquity: -45,
    impactCrypto: -75,
    impactFixedIncome: 8,
    impactCash: 0
  },
  {
    name: 'Tech Sector Correction',
    description: 'Valuation bubble bursts in AI and major semiconductors. High tech shares lose ground rapidly.',
    impactEquity: -25,
    impactCrypto: -15,
    impactFixedIncome: 2,
    impactCash: 0
  },
  {
    name: 'Inflationary Shock & Rate Hikes',
    description: 'Federal Reserve rises rates by 200bps unexpectedly. Growth stocks and long duration bonds suffer.',
    impactEquity: -18,
    impactCrypto: -35,
    impactFixedIncome: -12,
    impactCash: 0
  },
  {
    name: 'Crypto Winter',
    description: 'Regulatory crackdown on DeFi and stablecoins triggers a widespread capital flight from digital assets.',
    impactEquity: -2,
    impactCrypto: -65,
    impactFixedIncome: 0,
    impactCash: 0
  },
  {
    name: 'Green Energy / Post-Scarcity Boom',
    description: 'Breakthroughs in commercial fusion power. Tech and industry see a massive, unprecedented bull run.',
    impactEquity: 35,
    impactCrypto: 50,
    impactFixedIncome: -4,
    impactCash: 0
  }
];

export function runStressTest(holdings: Holding[], scenario: StressScenario) {
  let initialTotal = 0;
  let stressTotal = 0;

  const results = holdings.map(h => {
    const value = h.shares * h.currentPrice;
    initialTotal += value;

    // Base impact by asset class
    let baseImpact = 0;
    if (h.category === 'Equity') baseImpact = scenario.impactEquity;
    else if (h.category === 'Crypto') baseImpact = scenario.impactCrypto;
    else if (h.category === 'FixedIncome') baseImpact = scenario.impactFixedIncome;
    else if (h.category === 'Cash') baseImpact = scenario.impactCash;

    // Beta-adjust equity impacts (riskScore = beta * 4, market beta = 1.0 → score 4)
    let pctChange = baseImpact;
    if (h.category === 'Equity' && baseImpact !== 0) {
      const beta = Math.max(0.1, (h.riskScore ?? 4) / 4);
      pctChange = Math.max(-95, Math.min(200, baseImpact * beta));
    }

    const stressValue = value * (1 + pctChange / 100);
    stressTotal += stressValue;

    return {
      symbol: h.symbol,
      name: h.name,
      category: h.category,
      initialValue: value,
      stressedValue: stressValue,
      difference: stressValue - value,
      pctChange: parseFloat(pctChange.toFixed(1))
    };
  });

  const totalDifference = stressTotal - initialTotal;
  const totalPctChange = initialTotal > 0 ? (totalDifference / initialTotal) * 100 : 0;

  return {
    scenarioName: scenario.name,
    initialTotal,
    stressTotal,
    totalDifference,
    totalPctChange,
    results
  };
}

export type CorrMatrix = {
  symbols: string[];
  matrix: { symbol: string; correlations: { symbol: string; value: number; commonDays: number }[] }[];
};

export function computeCorrelationMatrix(
  priceHistories: Record<string, { date: string; price: number }[]>
): CorrMatrix {
  const symbols = Object.keys(priceHistories).filter(s => priceHistories[s].length > 2);
  if (symbols.length === 0) return { symbols: [], matrix: [] };

  // Build daily-return maps per symbol
  const returnMaps: Record<string, Record<string, number>> = {};
  for (const sym of symbols) {
    returnMaps[sym] = {};
    const sorted = [...priceHistories[sym]].sort((a, b) => a.date.localeCompare(b.date));
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1].price;
      if (prev > 0) returnMaps[sym][sorted[i].date] = (sorted[i].price - prev) / prev;
    }
  }

  function pearson(r1: number[], r2: number[]): number {
    const n = r1.length;
    if (n < 2) return 0;
    const m1 = r1.reduce((a, b) => a + b, 0) / n;
    const m2 = r2.reduce((a, b) => a + b, 0) / n;
    let num = 0, d1 = 0, d2 = 0;
    for (let i = 0; i < n; i++) {
      const a = r1[i] - m1, b = r2[i] - m2;
      num += a * b; d1 += a * a; d2 += b * b;
    }
    return d1 > 0 && d2 > 0 ? num / Math.sqrt(d1 * d2) : 0;
  }

  const matrix = symbols.map(sym1 => ({
    symbol: sym1,
    correlations: symbols.map(sym2 => {
      if (sym1 === sym2) return { symbol: sym2, value: 1.0, commonDays: Object.keys(returnMaps[sym1]).length };
      const commonDates = Object.keys(returnMaps[sym1]).filter(d => d in returnMaps[sym2]);
      const r1 = commonDates.map(d => returnMaps[sym1][d]);
      const r2 = commonDates.map(d => returnMaps[sym2][d]);
      return { symbol: sym2, value: parseFloat(pearson(r1, r2).toFixed(2)), commonDays: commonDates.length };
    })
  }));

  return { symbols, matrix };
}
