// COA — proxy serverless para a API da Anthropic (Vercel)
// Mantém a chave no servidor. Definir ANTHROPIC_API_KEY em Project Settings -> Environment Variables.
// Limite de corpo da requisição na Vercel: ~4,5 MB — o front end valida o tamanho
// dos PDFs antes de enviar (ver app.html). O timeout da função está em vercel.json.

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return res.status(500).json({ error: 'ANTHROPIC_API_KEY not configured' });

  const { content } = req.body || {};
  if (!Array.isArray(content) || content.length === 0)
    return res.status(400).json({ error: 'Missing content' });

  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: 'claude-opus-4-8',
        max_tokens: 8192,
        messages: [{ role: 'user', content }]
      })
    });
    const data = await r.json();
    if (!r.ok) return res.status(r.status).json({ error: data.error?.message || 'Upstream error' });
    if (data.stop_reason === 'refusal')
      return res.status(200).json({ refusal: true });  // o front end mostra a mensagem no idioma do usuário
    const text = (data.content || []).map(i => (i.type === 'text' ? i.text : '')).join('\n');
    return res.status(200).json({ text });
  } catch (e) {
    return res.status(500).json({ error: e.message });
  }
}
