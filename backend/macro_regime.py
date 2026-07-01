"""
macro_regime.py — Makro rejim analizi modulu

GENEL gostergeler (tum piyasalar):
  1. VIX (yfinance ^VIX)                         — korku / volatilite
  2. Getiri egrisi 10Y-2Y (yfinance ^TNX, 2YY=F) — resesyon riski
  3. USD/TRY trend (yfinance USDTRY=X, 90g HA)   — yerel kur rejimi

BIST-OZEL gostergeler (tcmb_evds.py uzerinden, key gerekir):
  4. TCMB Politika Faizi trendi (TP.TF.UN2)      — faiz siklasmasi
  5. TUFE yillik enflasyon trendi (TP.FG.J0)     — enflasyon baskisi
  6. Yabanci Portfoy Net Akisi (TP.DPB.S01)      — yabanci ilgisi

Calismayan kaynaklar:
  - CAPE / Shiller PE  : multpl.com JS-rendered
  - AAII Sentiment     : HTTP 403
  - CBOE Put/Call Orani: HTTP 403
  - BIST Yabanci Net   : MKK endpoint 404 (EVDS ile cozuldu)

risk_off_score      : genel, US ve BIST alimlarini etkiler
bist_risk_off_score : BIST-ozel ek katman (TCMB verisiyle zenginlestir)
"""

from __future__ import annotations
import time
from typing import Optional
import pandas as pd
import twelve_data as td

_CACHE: dict = {}
_CACHE_TTL = 3600  # saniye


def _fetch_vix() -> dict:
    """VIX degerini ceker (VXX proxy'si uzerinden). VXX<25: dusuk risk, VXX>40: yuksek risk."""
    try:
        val = td.get_price("^VIX")
        if not val or val <= 0:
            return {"ok": False, "error": "VIX proxy (VXX) fiyati alinamadi"}
        # Normalize: 0.0 (risk-on, VXX<=22) → 1.0 (risk-off, VXX>=40)
        score = max(0.0, min(1.0, (val - 22.0) / (40.0 - 22.0)))
        return {"ok": True, "value": round(val, 2), "score": round(score, 3),
                "note": f"VIX Proxy (VXX)={val:.1f} ({'dusuk' if val < 25 else 'orta' if val < 35 else 'yuksek'})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _fetch_yield_curve() -> dict:
    """IEF/SHY spread proxy (10Y-2Y yield curve spread yerine)."""
    try:
        y10 = td.get_price("^TNX")
        y2 = td.get_price("2YY=F")
        if not y10 or not y2 or y10 <= 0 or y2 <= 0:
            return {"ok": False, "error": "Yield proxies (IEF/SHY) alinamadi"}
        
        ratio = y10 / y2
        spread = round(ratio - 1.15, 4)
        
        # Normalize: spread>0.02: 0.0 (risk-on), spread<0.0: 0.8+ (risk-off, inverted)
        if spread >= 0.02:
            score = 0.0
        elif spread >= 0:
            score = 0.6 * (1.0 - spread / 0.02)
        else:
            score = min(1.0, 0.6 + abs(spread) * 20.0)
            
        trend = "normal" if spread > 0 else ("duz" if spread > -0.01 else "ters (resesyon sinyali)")
        return {"ok": True, "y10": round(y10, 3), "y2": round(y2, 3),
                "spread": spread, "score": round(score, 3),
                "note": f"IEF={y10:.2f} SHY={y2:.2f} ratio={ratio:.4f} spread_proxy={spread:+.4f} ({trend})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _fetch_usdtry_trend() -> dict:
    """USD/TRY trendini 20/90 gunluk hareketli ortalamaya gore degerlendirir."""
    try:
        series = td.get_time_series("USDTRY=X", days=120, interval="1day")
        if not series or len(series) < 20:
            return {"ok": False, "error": "yetersiz gecmis veri"}
            
        closes = [float(p["close"]) for p in reversed(series)]
        current = closes[-1]
        
        df_close = pd.Series(closes)
        ma20 = float(df_close.rolling(20).mean().iloc[-1])
        ma90 = float(df_close.rolling(90).mean().iloc[-1]) if len(df_close) >= 90 else ma20
        
        deviation = (current - ma90) / ma90
        score = max(0.0, min(1.0, deviation / 0.10))
        trend = "guclenme" if current < ma90 else ("yatay" if abs(deviation) < 0.02 else "zayiflama")
        return {"ok": True, "current": round(current, 4), "ma20": round(ma20, 4),
                "ma90": round(ma90, 4), "deviation_pct": round(deviation * 100, 2),
                "score": round(score, 3),
                "note": f"USD/TRY={current:.4f} MA90={ma90:.4f} ({trend}, sapma={deviation*100:+.1f}%)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _compute_score(components: list[tuple[str, float, dict]]) -> tuple[float, float]:
    """(score, key, data) listesinden agirlikli skor hesaplar. (weighted_score, total_weight) doner."""
    total_w = 0.0
    weighted = 0.0
    for _name, w, data in components:
        if data.get("ok"):
            weighted += data["score"] * w
            total_w += w
    return (round(weighted / total_w, 3) if total_w > 0 else 0.5), round(total_w, 2)


def get_market_regime(use_cache: bool = True) -> dict:
    """
    Aktif makro gostergeleri toplar, iki ayri risk skoru hesaplar:
      risk_off_score      : Genel (VIX + yield curve + USD/TRY) — US ve BIST icin ortak
      bist_risk_off_score : BIST-ozel (genel + TCMB faiz + TUFE + yabanci akim)
    deployment_multiplier      : US alimlarinda kullanilir (genel skora gore)
    bist_deployment_multiplier : BIST alimlarinda kullanilir (BIST skora gore)
    """
    now = time.time()
    if use_cache and _CACHE.get("ts") and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["result"]

    vix    = _fetch_vix()
    yield_ = _fetch_yield_curve()
    usdtry = _fetch_usdtry_trend()

    # ── Genel risk_off_score (US + BIST ortak taban) ──────────────────────────
    general_components = [
        ("vix",         0.50, vix),
        ("yield_curve", 0.30, yield_),
        ("usdtry",      0.20, usdtry),
    ]
    risk_off_score, gen_weight = _compute_score(general_components)

    # ── TCMB / BIST-ozel bilesenler (key yoksa pas gec) ──────────────────────
    tcmb_data: dict = {}
    policy_rate   = {"ok": False, "score": 0.5, "note": "TCMB key eksik"}
    inflation     = {"ok": False, "score": 0.5, "note": "TCMB key eksik"}
    foreign_equity = {"ok": False, "score": 0.5, "note": "TCMB key eksik"}
    tcmb_error: Optional[str] = None

    economic_health: dict = {}
    try:
        from tcmb_evds import get_tcmb_data
        tcmb_data = get_tcmb_data(use_cache=use_cache)
        policy_rate    = tcmb_data.get("policy_rate",    policy_rate)
        inflation      = tcmb_data.get("inflation",      inflation)
        foreign_equity = tcmb_data.get("foreign_equity", foreign_equity)
        economic_health = tcmb_data.get("economic_health_score", {})
    except RuntimeError as e:
        tcmb_error = str(e)  # key eksik — sessizce gec
    except Exception as e:
        tcmb_error = str(e)

    # BIST-ozel skor: genel taban (%50) + faiz (%20) + enflasyon (%15) + yabanci (%15)
    bist_components = [
        ("vix",            0.25, vix),
        ("yield_curve",    0.15, yield_),
        ("usdtry",         0.10, usdtry),
        ("policy_rate",    0.20, policy_rate),
        ("inflation",      0.15, inflation),
        ("foreign_equity", 0.15, foreign_equity),
    ]
    bist_risk_off_score, bist_weight = _compute_score(bist_components)

    def _multiplier(score: float) -> float:
        return round(max(0.5, 1.0 - score * 0.5), 3)

    def _label(score: float) -> str:
        return (
            "RISK-ON (normal dagitim)"  if score < 0.3 else
            "KARMA (kismi kisitlama)"   if score < 0.7 else
            "RISK-OFF (yari dagitim)"
        )

    result = {
        # Genel (US ve BIST ortak taban)
        "risk_off_score":        risk_off_score,
        "deployment_multiplier": _multiplier(risk_off_score),
        "regime":                _label(risk_off_score),
        # BIST-ozel
        "bist_risk_off_score":        bist_risk_off_score,
        "bist_deployment_multiplier": _multiplier(bist_risk_off_score),
        "bist_regime":                _label(bist_risk_off_score),
        # Gostergeler
        "indicators": {
            "vix":            vix,
            "yield_curve":    yield_,
            "usdtry_trend":   usdtry,
            "policy_rate":    policy_rate,
            "inflation":      inflation,
            "foreign_equity": foreign_equity,
        },
        "weights": {
            "general": {"vix": 0.50, "yield_curve": 0.30, "usdtry": 0.20},
            "bist":    {"vix": 0.25, "yield_curve": 0.15, "usdtry": 0.10,
                        "policy_rate": 0.20, "inflation": 0.15, "foreign_equity": 0.15},
        },
        "active_weight_general": gen_weight,
        "active_weight_bist":    bist_weight,
        "tcmb_status": (
            "ok"        if not tcmb_error and policy_rate.get("ok") else
            "key_eksik" if "TCMB_EVDS_API_KEY" in str(policy_rate.get("error", ""))
                           or "TCMB_EVDS_API_KEY" in str(tcmb_error or "") else
            f"hata: {tcmb_error or (tcmb_data.get('errors') or ['?'])[0]}"
        ),
        "skipped_sources": {
            "cape_shiller":   "multpl.com JS-rendered",
            "aaii_sentiment": "HTTP 403",
            "cboe_pcr":       "HTTP 403",
        },
        # economic_health_score composite'e girmez — sadece gösterim
        "economic_health_score": economic_health,
    }
    if tcmb_error:
        result["tcmb_error"] = tcmb_error

    _CACHE["ts"] = now
    _CACHE["result"] = result
    return result
