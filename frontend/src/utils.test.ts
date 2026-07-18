import { describe, expect, it } from 'vitest';
import { calculatePortfolio, convertCurrency, formatCurrency } from './utils';
import type { Holding } from './types';

function makeHolding(overrides: Partial<Holding> = {}): Holding {
  return {
    id: '1',
    symbol: 'AAPL',
    name: 'Apple Inc.',
    category: 'Equity',
    sector: 'Technology',
    shares: 10,
    avgBuyPrice: 100,
    currentPrice: 150,
    riskScore: 5,
    assetClass: 'ABD Hisse/ETF',
    ...overrides,
  };
}

describe('formatCurrency', () => {
  it('prefixes the correct symbol and formats two decimals', () => {
    expect(formatCurrency(1234.5, 'USD')).toBe('$1,234.50');
    expect(formatCurrency(1234.5, 'TRY')).toBe('₺1,234.50');
  });
});

describe('convertCurrency', () => {
  const rates = { usd_rate: 32, eur_rate: 35, gbp_rate: 40 };

  it('returns the same value when currencies match', () => {
    expect(convertCurrency(100, 'USD', 'USD', rates)).toBe(100);
  });

  it('returns 0 for a falsy value without touching rates', () => {
    expect(convertCurrency(0, 'USD', 'TRY', rates)).toBe(0);
  });

  it('converts USD to TRY using usd_rate', () => {
    expect(convertCurrency(10, 'USD', 'TRY', rates)).toBeCloseTo(320);
  });

  it('converts TRY to USD using usd_rate', () => {
    expect(convertCurrency(320, 'TRY', 'USD', rates)).toBeCloseTo(10);
  });

  it('falls back to usd_rate * 1.27 when gbp_rate is missing', () => {
    const noGbp = { usd_rate: 32, eur_rate: 35 };
    const expected = 10 * (32 * 1.27);
    expect(convertCurrency(10, 'GBP', 'TRY', noGbp)).toBeCloseTo(expected);
  });
});

describe('calculatePortfolio', () => {
  it('returns zeroed metrics for an empty portfolio', () => {
    const result = calculatePortfolio([]);
    expect(result.totalValue).toBe(0);
    expect(result.totalCost).toBe(0);
    expect(result.unrealizedPL).toBe(0);
    expect(result.unrealizedPLPercent).toBe(0);
    expect(result.portfolioRiskScore).toBe(0);
    expect(result.holdings).toEqual([]);
  });

  it('computes value, cost and unrealized P&L per holding', () => {
    const holding = makeHolding({ shares: 10, avgBuyPrice: 100, currentPrice: 150 });
    const result = calculatePortfolio([holding]);

    expect(result.totalValue).toBe(1500);
    expect(result.totalCost).toBe(1000);
    expect(result.unrealizedPL).toBe(500);
    expect(result.unrealizedPLPercent).toBeCloseTo(50);
    expect(result.holdings[0].unrealizedPL).toBe(500);
    expect(result.holdings[0].unrealizedPLPercent).toBeCloseTo(50);
  });

  it('does not divide by zero when avgBuyPrice/cost is zero', () => {
    const holding = makeHolding({ shares: 10, avgBuyPrice: 0, currentPrice: 150 });
    const result = calculatePortfolio([holding]);
    expect(result.holdings[0].unrealizedPLPercent).toBe(0);
  });

  it('computes a value-weighted portfolio risk score', () => {
    const low = makeHolding({ id: '1', shares: 10, avgBuyPrice: 100, currentPrice: 100, riskScore: 2 });
    const high = makeHolding({ id: '2', shares: 10, avgBuyPrice: 100, currentPrice: 100, riskScore: 8 });
    const result = calculatePortfolio([low, high]);
    // Eşit değerli iki pozisyon → basit ortalama
    expect(result.portfolioRiskScore).toBeCloseTo(5);
  });

  it('sorts allocation percentages by descending value and sums to ~100%', () => {
    const small = makeHolding({ id: '1', symbol: 'A', shares: 1, avgBuyPrice: 10, currentPrice: 10 });
    const big = makeHolding({ id: '2', symbol: 'B', shares: 100, avgBuyPrice: 10, currentPrice: 10 });
    const result = calculatePortfolio([small, big]);

    expect(result.holdings[0].symbol).toBe('B'); // büyük pozisyon önce gelmeli
    const totalPct = result.holdings.reduce((sum, h) => sum + h.allocationPercent, 0);
    expect(totalPct).toBeCloseTo(100);
  });

  it('classifies TEFAS funds and BIST stocks into detailed allocation buckets', () => {
    const fund = makeHolding({ id: '1', symbol: 'BIH', assetClass: 'TEFAS Fonu', category: 'FixedIncome' });
    const bist = makeHolding({ id: '2', symbol: 'THYAO.IS', assetClass: 'BIST Hissesi', category: 'Equity' });
    const cash = makeHolding({ id: '3', symbol: 'TRY-NAKIT', assetClass: 'Nakit', category: 'Cash' });
    const result = calculatePortfolio([fund, bist, cash]);

    const buckets = Object.fromEntries(result.detailedAllocations.map(a => [a.category, a.value]));
    expect(buckets['TEFAS_FUND']).toBeGreaterThan(0);
    expect(buckets['BIST_STOCK']).toBeGreaterThan(0);
    expect(buckets['CASH']).toBeGreaterThan(0);
  });

  it('groups a known ETF ticker separately from a regular US stock', () => {
    const etf = makeHolding({ id: '1', symbol: 'VOO', assetClass: 'ABD Hisse/ETF' });
    const stock = makeHolding({ id: '2', symbol: 'AAPL', assetClass: 'ABD Hisse/ETF' });
    const result = calculatePortfolio([etf, stock]);

    const buckets = Object.fromEntries(result.detailedAllocations.map(a => [a.category, a.value]));
    expect(buckets['US_ETF']).toBeGreaterThan(0);
    expect(buckets['US_STOCK']).toBeGreaterThan(0);
  });
});
