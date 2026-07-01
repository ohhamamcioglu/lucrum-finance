"""
Scanner'ı UTF-8 log dosyasına çalıştırır.
Tüm çıktı scan_log_kap_zf.txt dosyasına UTF-8 olarak yazılır.
"""
import sys, io, os

LOG = r"C:\Users\ohham\lucrum-finance-mcp\scan_log_kap_zf.txt"
log_fh = open(LOG, "w", encoding="utf-8", buffering=1)

sys.stdout = io.TextIOWrapper(log_fh.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = sys.stdout

os.chdir(r"C:\Users\ohham\lucrum-finance-mcp")

import scanner
sys.argv = ["scanner.py", "--subset", "bist100", "--kap"]
scanner.main()
