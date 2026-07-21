"""
COA — servidor de teste local (sem Node/Vercel).

Serve os arquivos estáticos da raiz do projeto e implementa POST /api/analyze
com o MESMO comportamento do api/analyze.js (proxy para a API da Anthropic),
para testar o fluxo completo do app sem deploy.

Uso:
  # Modo real (requer chave):
  export ANTHROPIC_API_KEY=sk-ant-...
  python3 scripts/dev_server.py

  # Modo mock (sem chave; devolve uma análise de exemplo para validar o fluxo):
  COA_MOCK=1 python3 scripts/dev_server.py

Depois abrir http://localhost:8000/app.html
"""
import json, os, sys, urllib.error, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

MOCK_TEXT = """[ANÁLISE DE EXEMPLO — MODO MOCK, sem chamada à API]

1) What you will pay
Your monthly assessment increases from $850 to $1,020 (+$170/month, +20.0%).
Calculation: 1,020 − 850 = 170; 170 ÷ 850 × 100 = 20.0%.

2) Where the money goes
Insurance: $612,000/year = $510 per unit per month (100 units).
Payroll: $240,000/year = $200 per unit per month.

3) Findings
F1. Insurance rose from $430,000 to $612,000 (+$182,000, +42.3%). Calculation: 612,000 − 430,000 = 182,000.
What many owners don't know: Florida condo insurance premiums are set per building, and boards can request competing quotes.
Question to ask: "How many insurance quotes did the board obtain before renewing?"

4) Documents worth requesting
- Current insurance policies
- Management services agreement

⚠️ This analysis is automated and may contain errors. It is not a substitute for an accountant or attorney."""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_POST(self):
        if self.path != "/api/analyze":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Invalid JSON"})
        content = body.get("content")
        if not isinstance(content, list) or not content:
            return self._json(400, {"error": "Missing content"})

        if os.environ.get("COA_MOCK"):
            return self._json(200, {"text": MOCK_TEXT})

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return self._json(500, {"error": "ANTHROPIC_API_KEY not configured (ou use COA_MOCK=1)"})
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": "claude-opus-4-8",
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": content}],
            }).encode(),
            headers={"Content-Type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            # espelha o analyze.js: corpo de erro pode não ser JSON (ex.: HTML de um 5xx do CDN)
            try:
                msg = json.loads(e.read() or b"{}")["error"]["message"]
            except Exception:
                msg = "Upstream error"
            return self._json(e.code, {"error": msg})
        except Exception as e:  # rede etc.
            return self._json(500, {"error": str(e)})
        if data.get("stop_reason") == "refusal":
            return self._json(200, {"refusal": True})
        text = "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return self._json(200, {"text": text})

    def _json(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    mode = "MOCK" if os.environ.get("COA_MOCK") else ("REAL" if os.environ.get("ANTHROPIC_API_KEY") else "SEM CHAVE")
    print(f"COA dev server em http://localhost:{PORT}/  (modo /api/analyze: {mode})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
