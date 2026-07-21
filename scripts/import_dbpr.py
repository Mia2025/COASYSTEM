"""
COA — Carga inicial de dados (v2.2) — mapeado para os arquivos públicos REAIS do DBPR.

Fontes (sem chave de API — downloads públicos gratuitos, atualizados semanalmente):
  Condomínios por região (5 arquivos):
    https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_MD.csv   (Dade, Monroe)
    https://www2.myfloridalicense.com/sto/file_download/extracts/condo_PB.csv   (Broward, Palm Beach)
    https://www2.myfloridalicense.com/sto/file_download/extracts/condo_CE.csv   (Central East)
    https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_CW.csv   (Central West)
    https://www2.myfloridalicense.com/sto/file_download/extracts/Condo_NF.csv   (North FL)
  Payment history (taxas anuais estaduais, 5 anos), dividido pela 1a letra:
    paymenthist_8002A/D/J/P/S/V.csv na mesma base.
  Sunbiz (diretores, status): arquivo trimestral em sunbiz.org (sem chave).
  SIRS: duas planilhas na página SIRS Reporting do DBPR (pré e pós jul/2025).
  Queixas CTMH por associação: via pedido de registros públicos (Chapter 119).

Colunas REAIS confirmadas (jul/2026):
  Condo_*.csv: Project Number, File Number, Condo Name, County,
    Street City State Zip, Units, Recorded Date (MM/DD/YYYY), Primary Status,
    Secondary Status, Managing Entity Number, Managing Entity Name,
    Managing Entity Route/Street/City/State/Zip
  paymenthist_*.csv: Program Area, Project County Code, Project Number,
    Project Name, Project Street, Project Address Line2, Project City/State/Zip,
    Billing Year, Amount Billed, Amount Paid, Pending Amount Due
  Observado na prática: Project Number é ÚNICO no cadastro de condomínios
  (0 duplicatas em 27.951 linhas) — por isso o import usa upsert por
  project_number e pode ser re-executado sem duplicar.

Uso:
  pip install pandas requests            # supabase só é necessário no modo Supabase
  # Modo Supabase (produção):
  export SUPABASE_URL=... SUPABASE_SERVICE_KEY=...
  # Modo local (teste sem Supabase): NÃO precisa das variáveis, passar --local
  python3 scripts/import_dbpr.py download                 # baixa os 11 arquivos -> ./data/
  python3 scripts/import_dbpr.py condos [--local arq.db]  # importa cadastro -> associations
  python3 scripts/import_dbpr.py payments [--local arq.db]
  python3 scripts/import_dbpr.py sirs lista_sirs.csv 2025-07+ [--local arq.db]
  python3 scripts/import_dbpr.py sunbiz sunbiz.csv [--local arq.db]

Notas importantes:
  - SIRS: importar a lista "pre-2025-07" ANTES da "2025-07+" (a última execução
    prevalece quando a associação aparece nas duas).
  - Matching por nome (sirs/sunbiz): nomes normalizados AMBÍGUOS (compartilhados
    por 2+ associações — ~900 casos nos extratos reais) são pulados e gravados
    em review_queue.csv para conferência manual, para não marcar o prédio errado.
"""
import os, re, sys, sqlite3
from datetime import datetime

import pandas as pd

BASE = "https://www2.myfloridalicense.com/sto/file_download/extracts/"
CONDO_FILES = ["Condo_MD.csv", "condo_PB.csv", "condo_CE.csv", "Condo_CW.csv", "Condo_NF.csv"]
PAY_FILES = ["paymenthist_8002A.csv", "paymenthist_8002D.csv", "paymenthist_8002J.csv",
             "paymenthist_8002P.csv", "paymenthist_8002S.csv", "paymenthist_8002V.csv"]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SUFFIXES = r"\b(inc|incorporated|llc|corp|corporation|assn|assoc|association|condominium|condo|the|of|a|at)\b"


def normalize(name):
    if not isinstance(name, str):
        return ""
    n = re.sub(r"[^\w\s]", " ", name.lower())
    n = re.sub(SUFFIXES, " ", n)
    return re.sub(r"\s+", " ", n).strip()


def iso_date(v):
    # DBPR usa MM/DD/YYYY; Postgres 'date' e SQLite preferem ISO
    v = (v or "").strip()
    if not v:
        return None
    try:
        return datetime.strptime(v, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _money(v):
    # vazio = desconhecido (None), não zero — ~9% das linhas de pagamento vêm em branco
    s = str(v).replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


CITY_ZIP = re.compile(r",\s*([^,]+?),?\s+FL\s+(\d{5})(?:-\d{4})?\s*$", re.IGNORECASE)


def split_city_zip(addr):
    # "8450 SW 133 AVENUE ROAD, MIAMI, FL 33183" -> ("MIAMI", "33183"); melhor esforço
    m = CITY_ZIP.search(addr or "")
    return (m.group(1).strip(), m.group(2)) if m else (None, None)


# ===== Backends: Supabase (produção) ou SQLite (teste local) =====

class SupabaseBackend:
    def __init__(self):
        from supabase import create_client  # import tardio: só exige o pacote neste modo
        self.client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    def upsert_associations(self, rows, batch=500):
        # Requer o índice único uq_assoc_project (ver COA_schema.sql v2.2)
        for i in range(0, len(rows), batch):
            self.client.table("associations").upsert(rows[i:i + batch], on_conflict="project_number").execute()
            print(f"associations upsert {min(i + batch, len(rows))}/{len(rows)}")

    def upsert_managers(self, rows, batch=500):
        for i in range(0, len(rows), batch):
            self.client.table("managers").upsert(rows[i:i + batch], on_conflict="license_number").execute()

    def _paged(self, cols):
        # PostgREST pagina em 1000 por padrão; .order garante paginação estável
        start = 0
        while True:
            res = self.client.table("associations").select(cols).order("id").range(start, start + 999).execute()
            for r in res.data:
                yield r
            if len(res.data) < 1000:
                return
            start += 1000

    def assoc_index(self):
        return {r["project_number"]: r["id"] for r in self._paged("id,project_number") if r.get("project_number")}

    def ambiguous_norms(self):
        seen, dup = set(), set()
        for r in self._paged("name_normalized"):
            n = r.get("name_normalized") or ""
            (dup if n in seen else seen).add(n)
        return dup

    def replace_payments(self, rows, batch=500):
        # id é PK uuid (nunca nulo) — filtro sempre-verdadeiro para apagar TODAS as linhas,
        # inclusive as com billing_year nulo (um .neq em billing_year deixaria essas para trás)
        self.client.table("association_payments").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        for i in range(0, len(rows), batch):
            self.client.table("association_payments").insert(rows[i:i + batch]).execute()
            print(f"payments insert {min(i + batch, len(rows))}/{len(rows)}")

    def update_by_name_norm(self, values, name_norm):
        res = self.client.table("associations").update(values).eq("name_normalized", name_norm).execute()
        return len(res.data or [])


class SQLiteBackend:
    """Espelho local mínimo do schema, para validar o import sem Supabase."""

    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.executescript("""
        create table if not exists associations (
          id integer primary key,
          name text, name_normalized text, address text, city text, county text, zip text,
          unit_count integer, dbpr_number text, sunbiz_doc_number text, status text,
          registered_agent text, match_confidence real,
          project_number text unique, file_number text, recorded_date text,
          sirs_filed integer, sirs_filed_period text
        );
        create index if not exists idx_assoc_norm on associations (name_normalized);
        create table if not exists managers (
          name text, license_number text unique, license_type text
        );
        create table if not exists association_payments (
          association_id integer, project_number text, billing_year integer,
          amount_billed real, amount_paid real, amount_due real
        );
        """)

    def upsert_associations(self, rows, batch=500):
        cols = ["name", "name_normalized", "city", "zip", "county", "address", "unit_count",
                "project_number", "file_number", "dbpr_number", "status", "recorded_date", "match_confidence"]
        upd = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "project_number")
        self.con.executemany(
            f"insert into associations ({','.join(cols)}) values ({','.join('?' * len(cols))}) "
            f"on conflict(project_number) do update set {upd}",
            [[r.get(c) for c in cols] for r in rows])
        self.con.commit()
        print(f"associations upsert {len(rows)} (sqlite)")

    def upsert_managers(self, rows, batch=500):
        self.con.executemany(
            "insert into managers (name, license_number) values (?, ?) "
            "on conflict(license_number) do update set name=excluded.name",
            [[r.get("name"), r.get("license_number")] for r in rows])
        self.con.commit()

    def assoc_index(self):
        return {pn: i for i, pn in self.con.execute(
            "select id, project_number from associations where project_number is not null")}

    def ambiguous_norms(self):
        return {n for (n,) in self.con.execute(
            "select name_normalized from associations group by name_normalized having count(*) > 1")}

    def replace_payments(self, rows, batch=500):
        self.con.execute("delete from association_payments")
        cols = ["association_id", "project_number", "billing_year", "amount_billed", "amount_paid", "amount_due"]
        self.con.executemany(
            f"insert into association_payments ({','.join(cols)}) values ({','.join('?' * len(cols))})",
            [[r.get(c) for c in cols] for r in rows])
        self.con.commit()
        print(f"payments insert {len(rows)} (sqlite)")

    def update_by_name_norm(self, values, name_norm):
        sets = ", ".join(f"{k}=?" for k in values)
        cur = self.con.execute(f"update associations set {sets} where name_normalized=?",
                               list(values.values()) + [name_norm])
        self.con.commit()
        return cur.rowcount


def backend(args):
    if "--local" in args:
        i = args.index("--local")
        path = args[i + 1] if len(args) > i + 1 else "coa_local.db"
        print(f"modo LOCAL (sqlite): {path}")
        return SQLiteBackend(path)
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        sys.exit("SUPABASE_URL/SUPABASE_SERVICE_KEY não definidos. Para testar sem Supabase use: --local [arquivo.db]")
    return SupabaseBackend()


# ===== Etapas =====

def download():
    import requests
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in CONDO_FILES + PAY_FILES:
        url = BASE + f
        print("baixando", url)
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        open(os.path.join(DATA_DIR, f), "wb").write(r.content)
    print("ok ->", DATA_DIR)


def read_csv_loose(path):
    # Arquivos DBPR: CSV entre aspas; tolerar encoding latin-1 e linhas quebradas
    return pd.read_csv(path, dtype=str, encoding="latin-1", on_bad_lines="skip").fillna("")


def load_condos():
    frames = []
    for f in CONDO_FILES:
        p = os.path.join(DATA_DIR, f)
        if not os.path.exists(p):
            sys.exit(f"faltando {p} — rode: python3 scripts/import_dbpr.py download")
        df = read_csv_loose(p)
        df.columns = [c.strip() for c in df.columns]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def import_condos(db):
    df = load_condos()
    rows, mans, seen = [], {}, set()
    for _, r in df.iterrows():
        name, proj = r.get("Condo Name", ""), r.get("Project Number", "").strip()
        if not name or not proj or proj in seen:
            continue
        seen.add(proj)
        units = str(r.get("Units", "")).strip()
        addr = r.get("Street City State Zip", "")
        city, zip_ = split_city_zip(addr)
        rows.append({
            "name": name, "name_normalized": normalize(name),
            "county": r.get("County", ""), "address": addr, "city": city, "zip": zip_,
            "unit_count": int(units) if units.isdigit() else None,
            "project_number": proj, "file_number": r.get("File Number", ""),
            "dbpr_number": r.get("Managing Entity Number", ""),
            "status": r.get("Primary Status", ""),
            "recorded_date": iso_date(r.get("Recorded Date")),
            "match_confidence": 1.0,   # direto da fonte oficial
        })
        me_name, me_num = r.get("Managing Entity Name", "").strip(), r.get("Managing Entity Number", "").strip()
        if me_name and me_num:
            mans[me_num] = me_name
    db.upsert_associations(rows)
    db.upsert_managers([{"name": v, "license_number": k} for k, v in mans.items()])
    print(f"condos: {len(rows)} associações, {len(mans)} administradoras")


def import_payments(db):
    idx = db.assoc_index()
    if not idx:
        sys.exit("associations vazio — rode primeiro: python3 scripts/import_dbpr.py condos")
    rows, unmatched = [], 0
    for f in PAY_FILES:
        p = os.path.join(DATA_DIR, f)
        if not os.path.exists(p):
            print("aviso: faltando", p)
            continue
        df = read_csv_loose(p)
        df.columns = [c.strip() for c in df.columns]
        for _, r in df.iterrows():
            num = str(r.get("Project Number", "")).strip()
            aid = idx.get(num)
            if aid is None:
                unmatched += 1
            yr = str(r.get("Billing Year", "")).strip()
            rows.append({
                "association_id": aid, "project_number": num,
                "billing_year": int(yr) if yr.isdigit() else None,
                "amount_billed": _money(r.get("Amount Billed")),
                "amount_paid": _money(r.get("Amount Paid")),
                "amount_due": _money(r.get("Pending Amount Due")),
            })
    db.replace_payments(rows)
    print(f"payments: {len(rows)} linhas ({unmatched} sem associação correspondente — projetos fora do cadastro atual)")


def _review_queue(rows):
    if not rows:
        return
    path = os.path.join(os.path.dirname(DATA_DIR), "review_queue.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"revisão manual: {len(rows)} nomes ambíguos/sem match -> {path}")


def mark_sirs(db, path, period):
    df = read_csv_loose(path)
    namecol = df.columns[0]
    ambiguous = db.ambiguous_norms()
    hits = misses = 0
    review = []
    for _, r in df.iterrows():
        raw = str(r[namecol])
        n = normalize(raw)
        if not n:
            continue
        if n in ambiguous:
            review.append({"source": "sirs", "name": raw, "reason": "nome compartilhado por 2+ associações"})
            continue
        c = db.update_by_name_norm({"sirs_filed": True, "sirs_filed_period": period}, n)
        hits += 1 if c else 0
        if not c:
            misses += 1
            review.append({"source": "sirs", "name": raw, "reason": "sem match de nome"})
    _review_queue(review)
    print(f"SIRS ({period}): {hits} marcadas, {misses} sem match, {len(review) - misses} ambíguas")


def enrich_sunbiz(db, path):
    df = read_csv_loose(path)
    col = lambda *names: next((c for c in df.columns for n in names if n.lower() in c.lower()), None)
    c_name = col("CORP_NAME", "COR_NAME", "Name")
    c_doc = col("DOC_NUMBER", "COR_NUMBER", "Document")
    c_ra = col("RA_NAME", "R_A_NAME", "Agent")
    if not c_name:
        sys.exit(f"não achei a coluna de nome no arquivo Sunbiz; colunas: {list(df.columns)[:10]}")
    ambiguous = db.ambiguous_norms()
    hits = 0
    review = []
    for _, r in df.iterrows():
        raw = str(r.get(c_name, ""))
        n = normalize(raw)
        if not n:
            continue
        if n in ambiguous:
            review.append({"source": "sunbiz", "name": raw, "reason": "nome compartilhado por 2+ associações"})
            continue
        hits += db.update_by_name_norm({
            "sunbiz_doc_number": r.get(c_doc, "") if c_doc else "",
            "registered_agent": r.get(c_ra, "") if c_ra else "",
        }, n)
    _review_queue(review)
    print("sunbiz: matches aplicados:", hits)


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "download":
        download()
    elif cmd == "condos":
        import_condos(backend(args))
    elif cmd == "payments":
        import_payments(backend(args))
    elif cmd == "sirs":
        mark_sirs(backend(args), args[1], args[2])
    elif cmd == "sunbiz":
        enrich_sunbiz(backend(args), args[1])
    else:
        print(__doc__)
