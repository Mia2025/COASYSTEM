# COA — Guia de operação (PT-BR)

Ordem recomendada: **GitHub → Vercel → domínio**. O Supabase fica para depois —
o site, a análise de orçamento e as cartas funcionam sem ele.

## 1. Subir para o GitHub (sem terminal)
1. Entrar em github.com → **New repository** → nome `coa-app` → Private → Create.
2. Na tela do repositório novo, clicar em **"uploading an existing file"**.
3. Arrastar **a pasta inteira** extraída do zip (arrastar a pasta, não os
   arquivos selecionados — assim os arquivos ocultos `.vercelignore` e
   `.gitignore` vão junto).
4. Commit changes.
5. Conferir na lista de arquivos do repositório que aparecem:
   `index.html`, `app.html`, `api/analyze.js`, `vercel.json`, `package.json`
   e `.vercelignore`. Se `.vercelignore` não aparecer, criar pelo botão
   Add file → Create new file e colar o conteúdo dele.

## 2. Deploy na Vercel
1. vercel.com → **Add New → Project** → importar o repositório `coa-app`.
2. Não mudar nenhuma configuração de build (é site estático + api/) → **Deploy**.
3. Depois do deploy: **Settings → Environment Variables** → adicionar
   `ANTHROPIC_API_KEY` = chave criada em console.anthropic.com → Save →
   **Deployments → Redeploy** (para a variável valer).
4. Testar: abrir `https://SEU-PROJETO.vercel.app/app.html`, enviar um PDF de
   orçamento e conferir o relatório. (Há um PDF de teste em
   `fixtures/budget_sample.pdf`.)
5. Se o deploy reclamar de `maxDuration`: abrir `vercel.json` e trocar 300 por 60.

## 3. Domínio (quando quiser)
Seguir a seção "Custom domain — condoownersalliance.com" do README
(A record `76.76.21.21` no apex, CNAME `cname.vercel-dns.com` no www).

## 4. Supabase — DEPOIS (dados dos 27.951 condomínios, casos, login)
Nada do site depende disso hoje. Quando decidir ativar:
1. Criar projeto em supabase.com → SQL Editor → colar `db/COA_schema.sql` → Run.
2. Authentication → Email (magic link) · Storage → bucket `documents` (privado).
3. No computador:
   ```bash
   cd coa-app
   export SUPABASE_URL=https://SEU-PROJETO.supabase.co
   export SUPABASE_SERVICE_KEY=eyJ...   # chave service_role (secreta!)
   python3 scripts/check_supabase.py    # confere conexão e tabelas
   pip3 install --user supabase pandas requests
   python3 scripts/import_dbpr.py download
   python3 scripts/import_dbpr.py condos
   python3 scripts/import_dbpr.py payments
   ```
   (Já validei tudo isso localmente: 27.951 associações, 140.954 pagamentos,
   re-execução sem duplicar. Para ensaiar sem Supabase: `--local arq.db`.)

## Teste local a qualquer momento (sem deploy)
```bash
COA_MOCK=1 python3 scripts/dev_server.py     # mock, sem gastar API
# ou com análise real:
ANTHROPIC_API_KEY=sk-ant-... python3 scripts/dev_server.py
```
Abrir http://localhost:8000/app.html e enviar `fixtures/budget_sample.pdf`.

## Limites conhecidos
- PDFs somados até ~3 MB por análise (limite de corpo da Vercel; o app avisa).
- SIRS e Sunbiz dependem de arquivos que chegam por download manual/pedido
  público — os comandos `sirs` e `sunbiz` já estão prontos (nomes ambíguos vão
  para `review_queue.csv` em vez de marcar o prédio errado).
