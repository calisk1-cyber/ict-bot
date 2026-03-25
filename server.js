require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());

// Statik dosyaları sun (index.html vs.)
app.use(express.static(path.join(__dirname)));

// Flask API (Python Bot) Proxy
app.get('/api/:endpoint', async (req, res) => {
  try {
    const url = `http://127.0.0.1:5000/api/${req.params.endpoint}`;
    console.log(`[PROXY] İstek yapılıyor: ${url}`);
    const response = await fetch(url);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error(`[HATA] Proxy (GET): ${err.message}`);
    res.status(500).json({ error: { message: `Flask'a bağlanılamadı: ${err.message}` } });
  }
});

app.post('/api/toggle_bot', async (req, res) => {
  try {
    const url = 'http://127.0.0.1:5000/api/toggle_bot';
    console.log(`[PROXY] İstek yapılıyor: ${url}`);
    const response = await fetch(url, { method: 'POST' });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error(`[HATA] Proxy (POST): ${err.message}`);
    res.status(500).json({ error: { message: `Flask'a bağlanılamadı: ${err.message}` } });
  }
});

// Groq API proxy endpoint
app.post('/api/analyze', async (req, res) => {
  // Mevcut Groq logic'i burda kalıyor (Flask veya Groq seçimi yapılabilir)
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: { message: 'GROQ_API_KEY bulunamadı.' } });
  }
  const { system, messages } = req.body;
  const groqMessages = [];
  if (system) groqMessages.push({ role: 'system', content: system });
  (messages || []).forEach(m => groqMessages.push({ role: m.role, content: m.content }));

  const groqBody = {
    model: 'llama-3.3-70b-versatile',
    messages: groqMessages,
    max_tokens: 4000,
    temperature: 0.7
  };

  try {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify(groqBody)
    });
    const data = await response.json();
    const text = data?.choices?.[0]?.message?.content || '';
    res.json({ content: [{ type: 'text', text }] });
  } catch (err) {
    res.status(500).json({ error: { message: `Sunucu hatası: ${err.message}` } });
  }
});

app.listen(PORT, () => {
  console.log(`\n✅ AI Hedge Fund sunucusu çalışıyor! (Groq - Llama 3.3 70B)`);
  console.log(`🌐 Tarayıcıda aç: http://localhost:${PORT}`);
  console.log(`\nDurdurmak için: Ctrl+C\n`);
});
