"""
tcmb_evds.py — TCMB EVDS API istemcisi (evds paketi üzerinden)
API Key: .env dosyasında TCMB_EVDS_API_KEY değişkeni olarak saklanır.

PDF kılavuzu notu: key query string DEĞİL header içinde gönderilmeli.
evds paketi (pip install evds) bu detayı doğru halleder.

Kullanılan seriler:
  TP.APIFON4      : TCMB Ağırlıklı Ortalama Fonlama Maliyeti (politika faizi yaklaşığı)
  TP.FG.J0        : TÜFE Genel Endeksi (formulas=3 → Yıllık % Değişim)
  TP.MKNETHAR.M7  : Yurt Dışı Yerleşikler Hisse Senedi Net Değişim (milyon USD)
"""

from __future__ import annotations
import os, time
from typing import Optional

_CACHE: dict = {}
_CACHE_TTL = 3600 * 6  # 6 saat


def _get_client():
    """evdsAPI istemcisi döner; key .env'den okunur."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass
    key = os.environ.get("TCMB_EVDS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "TCMB_EVDS_API_KEY eksik. "
            ".env dosyasına TCMB_EVDS_API_KEY=<key> satırını ekleyin."
        )
    from evds import evdsAPI
    return evdsAPI(key)


def discover_series(keyword: str, max_results: int = 20) -> list[dict]:
    """
    Anahtar kelimeyle EVDS seri kataloğunda arama yapar.
    Kullanım: discover_series("repo") veya discover_series("tufe")
    """
    try:
        client = _get_client()
        cats = client.main_categories
        results = []
        for _, row in cats.iterrows():
            title = str(row.get("TOPIC_TITLE_TR", ""))
            if keyword.lower() in title.lower():
                results.append({
                    "category_id": row.get("CATEGORY_ID"),
                    "title": title,
                })
        return results[:max_results] if results else [{"note": f"'{keyword}' için ana kategoride sonuç yok"}]
    except Exception as e:
        return [{"_error": str(e)}]


def _fetch_df(series_code: str, start: str, end: str,
              frequency: int = 5, formulas: int = 0) -> "Optional[object]":
    """evds paketi ile DataFrame çeker. None → hata."""
    try:
        client = _get_client()
        kwargs = {"startdate": start, "enddate": end, "frequency": frequency}
        if formulas:
            kwargs["formulas"] = formulas
        df = client.get_data([series_code], **kwargs)
        return df if not df.empty else None
    except Exception:
        return None


def _last_values(df, col_hint: str, n: int = 6) -> list[tuple[str, float]]:
    """DataFrame'den son n (tarih, değer) çiftini çıkarır."""
    if df is None:
        return []
    # Sütun adı: noktalar → alt çizgi, tireler kalır (TP.FG.J0-3 → TP_FG_J0-3)
    col = None
    for c in df.columns:
        if c.upper().replace(".", "_").startswith(col_hint.upper().replace(".", "_")):
            col = c
            break
    if col is None:
        # ilk sayısal sütun
        nums = [c for c in df.columns if c != "Tarih"]
        col = nums[0] if nums else None
    if col is None:
        return []
    result = []
    for _, row in df.iterrows():
        tarih = str(row.get("Tarih", ""))
        try:
            val = float(row[col])
            if val == val:  # NaN kontrolü
                result.append((tarih, val))
        except (ValueError, TypeError):
            pass
    return result[-n:]


def get_tcmb_data(use_cache: bool = True) -> dict:
    """
    TCMB politika faizi, TÜFE enflasyonu ve yabancı portföy verisini çeker.
    Döner: {policy_rate, inflation, foreign_equity, errors}
    """
    now = time.time()
    if use_cache and _CACHE.get("tcmb_ts") and (now - _CACHE["tcmb_ts"]) < _CACHE_TTL:
        return _CACHE["tcmb_result"]

    from datetime import date, timedelta
    end = date.today()
    start_str = (end - timedelta(days=240)).strftime("%d-%m-%Y")
    end_str = end.strftime("%d-%m-%Y")

    result: dict = {"errors": []}

    # ── 1. Politika Faizi (TCMB Ağırlıklı Ortalama Fonlama Maliyeti) ──────────
    try:
        df = _fetch_df("TP.APIFON4", start_str, end_str, frequency=5)
        vals = _last_values(df, "TP_APIFON4", n=6)
        if vals:
            latest_date, latest_rate = vals[-1]
            prev_rate = vals[-4][1] if len(vals) >= 4 else vals[0][1]
            trend = ("artis"  if latest_rate > prev_rate + 0.5 else
                     "dusus"  if latest_rate < prev_rate - 0.5 else
                     "sabit")
            score = 1.0 if trend == "artis" else (0.0 if trend == "dusus" else 0.4)
            result["policy_rate"] = {
                "ok": True,
                "latest": latest_rate,
                "latest_date": latest_date,
                "prev_3m": prev_rate,
                "trend": trend,
                "score": score,
                "note": f"TCMB fonlama=%{latest_rate:.2f} (3ay önce=%{prev_rate:.2f}, trend={trend})",
                "series": "TP.APIFON4",
            }
        else:
            result["policy_rate"] = {"ok": False, "error": "boş veri", "series": "TP.APIFON4"}
    except Exception as e:
        result["policy_rate"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"policy_rate: {e}")

    # ── 2. TÜFE Yıllık % Değişim (formulas=3) ────────────────────────────────
    try:
        df2 = _fetch_df("TP.FG.J0", start_str, end_str, frequency=5, formulas=3)
        vals2 = _last_values(df2, "TP_FG_J0", n=6)
        if vals2:
            latest_date, latest_inf = vals2[-1]
            prev_inf = vals2[-4][1] if len(vals2) >= 4 else vals2[0][1]
            trend = ("yukselis" if latest_inf > prev_inf + 1.0 else
                     "dusus"   if latest_inf < prev_inf - 1.0 else
                     "yatay")
            score = 1.0 if trend == "yukselis" else (0.0 if trend == "dusus" else 0.3)
            result["inflation"] = {
                "ok": True,
                "latest": round(latest_inf, 2),
                "latest_date": latest_date,
                "prev_3m": round(prev_inf, 2),
                "trend": trend,
                "score": score,
                "note": f"TÜFE=%{latest_inf:.1f} yıllık (3ay önce=%{prev_inf:.1f}, trend={trend})",
                "series": "TP.FG.J0 formulas=3",
            }
        else:
            result["inflation"] = {"ok": False, "error": "boş veri", "series": "TP.FG.J0"}
    except Exception as e:
        result["inflation"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"inflation: {e}")

    # ── 3. Yabancı Hisse Senedi Net Değişim ──────────────────────────────────
    try:
        df3 = _fetch_df("TP.MKNETHAR.M7", start_str, end_str, frequency=5)
        vals3 = _last_values(df3, "TP_MKNETHAR_M7", n=6)
        if vals3:
            latest_date, latest_flow = vals3[-1]
            last3 = [v for _, v in vals3[-3:]]
            avg_flow = sum(last3) / len(last3)
            trend = "giris" if avg_flow > 0 else "cikis"
            score = 1.0 if avg_flow < -500 else (0.5 if avg_flow < 0 else 0.0)
            result["foreign_equity"] = {
                "ok": True,
                "latest_mn_usd": round(latest_flow, 1),
                "latest_date": latest_date,
                "avg_3m_mn_usd": round(avg_flow, 1),
                "trend": trend,
                "score": score,
                "note": f"Yabancı hisse net={latest_flow:.0f}M USD (3ay ort={avg_flow:.0f}M, {trend})",
                "series": "TP.MKNETHAR.M7",
            }
        else:
            result["foreign_equity"] = {"ok": False, "error": "boş veri", "series": "TP.MKNETHAR.M7"}
    except Exception as e:
        result["foreign_equity"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"foreign_equity: {e}")

    # ── 4. Sanayi Üretim Endeksi (Yıllık % Değişim) ─────────────────────────
    try:
        df4 = _fetch_df("TP.TSANAYMT2021.Y1", start_str, end_str, frequency=5, formulas=3)
        vals4 = _last_values(df4, "TP_TSANAYMT2021_Y1", n=4)
        if vals4:
            latest_date, latest_ip = vals4[-1]
            avg_ip = sum(v for _, v in vals4[-3:]) / min(3, len(vals4))
            trend = ("yukselis" if avg_ip > 2.0 else
                     "dusus"   if avg_ip < -1.0 else
                     "yatay")
            # risk: düşük/negatif üretim = riskli
            score = max(0.0, min(1.0, -avg_ip / 5.0 + 0.5)) if avg_ip < 5.0 else 0.0
            result["industrial_production"] = {
                "ok": True,
                "latest_pct": round(latest_ip, 2),
                "latest_date": latest_date,
                "avg_3m_pct": round(avg_ip, 2),
                "trend": trend,
                "score": round(score, 3),
                "note": f"Sanayi üretimi yıllık={latest_ip:.1f}% (3ay ort={avg_ip:.1f}%, {trend})",
                "series": "TP.TSANAYMT2021.Y1 formulas=3",
            }
        else:
            result["industrial_production"] = {"ok": False, "error": "boş veri", "series": "TP.TSANAYMT2021.Y1"}
    except Exception as e:
        result["industrial_production"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"industrial_production: {e}")

    # ── 5. Kapasite Kullanım Oranı ────────────────────────────────────────────
    try:
        df5 = _fetch_df("TP.KKO.MA", start_str, end_str, frequency=5)
        vals5 = _last_values(df5, "TP_KKO_MA", n=4)
        if vals5:
            latest_date, latest_kko = vals5[-1]
            prev_kko = vals5[-4][1] if len(vals5) >= 4 else vals5[0][1]
            trend = ("yukselis" if latest_kko > prev_kko + 0.5 else
                     "dusus"   if latest_kko < prev_kko - 0.5 else
                     "yatay")
            # score: <70% = 1.0 (risk), >80% = 0.0 (sağlıklı)
            score = max(0.0, min(1.0, (80.0 - latest_kko) / 10.0))
            result["capacity_utilization"] = {
                "ok": True,
                "latest_pct": round(latest_kko, 1),
                "latest_date": latest_date,
                "prev_3m": round(prev_kko, 1),
                "trend": trend,
                "score": round(score, 3),
                "note": f"KKO=%{latest_kko:.1f} (3ay önce=%{prev_kko:.1f}, {trend})",
                "series": "TP.KKO.MA",
            }
        else:
            result["capacity_utilization"] = {"ok": False, "error": "boş veri", "series": "TP.KKO.MA"}
    except Exception as e:
        result["capacity_utilization"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"capacity_utilization: {e}")

    # ── 6. Cari Hesap (3 aylık) ───────────────────────────────────────────────
    try:
        df6 = _fetch_df("TP.ODANA6.Q01", start_str, end_str, frequency=6)
        vals6 = _last_values(df6, "TP_ODANA6_Q01", n=4)
        if vals6:
            latest_date, latest_ca = vals6[-1]
            avg_ca = sum(v for _, v in vals6[-2:]) / min(2, len(vals6))
            trend = ("fazla" if avg_ca > 0 else
                     "kucuk_acik" if avg_ca > -10000 else
                     "buyuk_acik")
            # score: cari açık büyük → risk (0=-30000M, 1=+10000M ters)
            score = max(0.0, min(1.0, -avg_ca / 25000.0))
            result["current_account"] = {
                "ok": True,
                "latest_mn_usd": round(latest_ca, 0),
                "latest_date": latest_date,
                "avg_2q_mn_usd": round(avg_ca, 0),
                "trend": trend,
                "score": round(score, 3),
                "note": f"Cari hesap={latest_ca:.0f}M USD ({trend})",
                "series": "TP.ODANA6.Q01",
            }
        else:
            result["current_account"] = {"ok": False, "error": "boş veri", "series": "TP.ODANA6.Q01"}
    except Exception as e:
        result["current_account"] = {"ok": False, "error": str(e)}
        result["errors"].append(f"current_account: {e}")

    # ── economic_health_score (display-only, composite'e girmiyor) ────────────
    ip  = result.get("industrial_production", {})
    cu  = result.get("capacity_utilization",  {})
    ca  = result.get("current_account",       {})
    ehs_parts = []
    if ip.get("ok"):  ehs_parts.append(("ip",  0.40, ip["score"]))
    if cu.get("ok"):  ehs_parts.append(("cu",  0.30, cu["score"]))
    if ca.get("ok"):  ehs_parts.append(("ca",  0.30, ca["score"]))
    if ehs_parts:
        total_w = sum(w for _, w, _ in ehs_parts)
        ehs = round(sum(w * s for _, w, s in ehs_parts) / total_w, 3)
        label = ("SAGLI KLI" if ehs < 0.35 else
                 "ORTA"      if ehs < 0.65 else
                 "ZAYIF")
        result["economic_health_score"] = {
            "score": ehs,
            "label": label,
            "components": {n: round(s, 3) for n, _, s in ehs_parts},
            "note": f"Ekonomik sağlık skoru={ehs:.3f} ({label}) — SADECE GÖSTERIM",
        }
    else:
        result["economic_health_score"] = {"score": None, "label": "veri yok"}

    _CACHE["tcmb_ts"] = now
    _CACHE["tcmb_result"] = result
    return result
