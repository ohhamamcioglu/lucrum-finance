"""
TCMB API'den USD/TRY kurunu al
"""
import requests
from datetime import datetime, timedelta

def get_current_usd_try_rate():
    """Guncel USD/TRY kurunun TCMB'den al"""
    try:
        # TCMB EVDS API
        url = "https://evds2.tcmb.gov.tr/service/getdata"

        # USD/TRY kuru (serieId: TP.DOLAR.S)
        params = {
            "series": "TP.DOLAR.S",
            "startDate": datetime.now().strftime("%d-%m-%Y"),
            "endDate": datetime.now().strftime("%d-%m-%Y"),
            "type": "json"
        }

        resp = requests.get(url, params=params, timeout=10)

        if resp.ok:
            data = resp.json()
            if data.get("success") and data.get("data"):
                items = data["data"]
                if items and len(items) > 0:
                    # Son kaydı al (guncel kur)
                    latest = items[0]
                    rate = float(latest["TP_DOLAR_S"])
                    print(f"[OK] TCMB USD/TRY: {rate}")
                    return rate

        print("[WARN] TCMB API cevap yok")
        return None

    except Exception as e:
        print(f"[ERROR] TCMB API: {e}")
        return None

def get_historical_usd_try_rate(date_str):
    """Belirli tarih icin USD/TRY kurunun al (YYYY-MM-DD formatinda)"""
    try:
        # Tarihi DD-MM-YYYY'ye cevir
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_param = date_obj.strftime("%d-%m-%Y")

        url = "https://evds2.tcmb.gov.tr/service/getdata"
        params = {
            "series": "TP.DOLAR.S",
            "startDate": date_param,
            "endDate": date_param,
            "type": "json"
        }

        resp = requests.get(url, params=params, timeout=10)

        if resp.ok:
            data = resp.json()
            if data.get("success") and data.get("data"):
                items = data["data"]
                if items and len(items) > 0:
                    rate = float(items[0]["TP_DOLAR_S"])
                    return rate

        return None

    except Exception as e:
        print(f"[WARN] TCMB tarihsel {date_str}: {e}")
        return None

if __name__ == "__main__":
    rate = get_current_usd_try_rate()
    if rate:
        print(f"Guncel oran: {rate}")

    hist = get_historical_usd_try_rate("2024-12-22")
    if hist:
        print(f"2024-12-22 orani: {hist}")
    else:
        print("Tarihsel veri alinamadi")
