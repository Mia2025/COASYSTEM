"""
COA — verificação da conexão Supabase (só stdlib, sem dependências).

Confere se SUPABASE_URL/SUPABASE_SERVICE_KEY funcionam e se as tabelas do
COA_schema.sql existem no projeto.

Uso:
  export SUPABASE_URL=https://SEU-PROJETO.supabase.co
  export SUPABASE_SERVICE_KEY=eyJ...
  python3 scripts/check_supabase.py
"""
import json, os, sys, urllib.request, urllib.error

TABLES = ["associations", "association_directors", "managers", "association_managers",
          "public_complaints", "profiles", "user_units", "cases", "case_events",
          "documents", "budget_analyses", "unit_prices", "association_metrics",
          "association_payments"]

url = os.environ.get("SUPABASE_URL", "").rstrip("/")
key = os.environ.get("SUPABASE_SERVICE_KEY", "")
if not url or not key:
    sys.exit("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY (ver .env.example)")

ok, missing, errors = [], [], []
for t in TABLES:
    req = urllib.request.Request(f"{url}/rest/v1/{t}?select=*&limit=1",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.loads(r.read())
        ok.append(t)
    except urllib.error.HTTPError as e:
        if e.code in (404, 400):
            missing.append(t)
        else:
            errors.append((t, e.code))
    except Exception as e:
        sys.exit(f"Falha de conexão com {url}: {e}")

print(f"Conexão OK: {url}")
print(f"Tabelas encontradas ({len(ok)}/{len(TABLES)}): {', '.join(ok) or '-'}")
if missing:
    print(f"FALTANDO ({len(missing)}): {', '.join(missing)}")
    print("-> Rode o db/COA_schema.sql no SQL Editor do Supabase.")
if errors:
    print(f"Erros de acesso: {errors}")
if not missing and not errors:
    print("Tudo pronto — pode rodar: python3 scripts/import_dbpr.py condos && python3 scripts/import_dbpr.py payments")
