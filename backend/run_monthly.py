import sys
sys.path.insert(0, r"C:\Users\ohham\lucrum-finance-mcp")

import types, importlib.util, os

_stub = types.ModuleType("mcp.server.fastmcp")
_stub.FastMCP = type("FastMCP", (), {"__init__": lambda s,*a,**k: None, "tool": lambda s: (lambda f: f), "run": lambda s: None})
sys.modules.setdefault("mcp", types.ModuleType("mcp"))
sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
sys.modules["mcp.server.fastmcp"] = _stub

spec = importlib.util.spec_from_file_location("server", r"C:\Users\ohham\lucrum-finance-mcp\server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

import json

result = srv.monthly_cycle(20000, dry_run=True)
out = json.dumps(result, ensure_ascii=False, indent=2, default=str)
with open(r"C:\Users\ohham\lucrum-finance-mcp\monthly_result.json", "w", encoding="utf-8") as f:
    f.write(out)
print("monthly_result.json yazildi.")

# ── Ozet ──────────────────────────────────────────────────────────────────────
cycle = result
def p(s=""):
    print(s.encode("ascii", errors="replace").decode("ascii"))

p()
p(f"Ay         : {cycle.get('month')}")
p(f"Butce      : {cycle.get('total_budget_tl')} TL")
p(f"BIST alim  : {len(cycle.get('bist_buys', []))}")
p(f"ABD alim   : {len(cycle.get('us_buys', []))}")
p(f"BIST havuz : {cycle.get('bist_pool_size')}")
p(f"ABD havuz  : {cycle.get('us_pool_size')}")
p(f"Kalan nakit: {cycle.get('leftover_tl')} TL")
p()

# ── Market regime dogrulamasi ─────────────────────────────────────────────────
p("=== MARKET REGIME (GOZLEM MODU DOGRULAMA) ===")
mr = cycle.get("market_regime", {})
p(f"  aktif_strateji     : {mr.get('aktif_strateji')}")
p(f"  deployment_multiplier (kullanilan): {mr.get('deployment_multiplier')}")
p(f"  regime_held_back_tl: {mr.get('regime_held_back_tl')}")
p()

sav = mr.get("savunmaci_filtre", {})
p("  -- Savunmaci filtre (gozlem) --")
p(f"    durum              : {sav.get('durum')}")
p(f"    risk_off_score     : {sav.get('risk_off_score')}")
p(f"    mult_obs           : {sav.get('deployment_multiplier_obs')}")
p(f"    regime             : {sav.get('regime')}")
p(f"    bist_risk_off_score: {sav.get('bist_risk_off_score')}")
p(f"    bist_mult_obs      : {sav.get('bist_mult_obs')}")
p()

kon = mr.get("kontraryen_filtre", {})
p("  -- Kontraryen filtre (gozlem) --")
p(f"    durum              : {kon.get('durum')}")
p(f"    vix                : {kon.get('vix')}")
p(f"    fear_score         : {kon.get('fear_score')}")
p(f"    contrarian_mult_obs: {kon.get('contrarian_mult_obs')}")
p(f"    signal             : {kon.get('signal')}")
p(f"    not                : {kon.get('not')}")
p()

p("BIST alimlari:")
for b in cycle.get("bist_buys", []):
    p(f"  {b.get('ticker'):<14} {b.get('allocated_tl')} TL  skor={b.get('composite_score')}")
p()
p("ABD alimlari:")
for b in cycle.get("us_buys", []):
    p(f"  {b.get('ticker'):<14} {b.get('allocated_tl')} TL  skor={b.get('composite_score')}")
