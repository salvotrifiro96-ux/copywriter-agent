# Copywriter Agent

Agente Streamlit del team marketing Leone. Tre modalità in un'unica app:

- **📣 Ads** — varianti per Meta (Facebook/Instagram), Google Search RSA, TikTok/Reels, LinkedIn Sponsored.
- **📧 Mail di conferma** — la mail post-iscrizione che consegna il lead magnet.
- **🌱 Nurturing** — sequenza intera o singola mail con ruolo specifico (bonding, pain-agitation, mechanism, proof, anti-objection, urgency-offer).

Stack: Streamlit + Anthropic SDK (`claude-sonnet-4-6`). Pattern identico agli altri agenti (`promise-writer-agent`, `funnel-landing-agent`).

## Setup locale

```bash
cd copywriter-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edita .env con la tua ANTHROPIC_API_KEY
streamlit run app.py
```

Apre su `http://localhost:8501`. Password gate: `faraone.92` (override via `APP_PASSWORD` in `.env` o secrets Streamlit Cloud).

## Setup Streamlit Cloud

1. Connetti il repo a Streamlit Cloud
2. Aggiungi su Settings → Secrets:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "faraone.92"
   ```

## Test

```bash
pytest
```

Solo unit test puri su parsing/utility. Niente chiamate API.

## Struttura

```
app.py                 → UI Streamlit (3 tab + sidebar condivisa)
agent/
  common.py            → helpers riusabili (JSON, sezioni, sanitizzazione)
  ads.py               → write_ads(channel, ...) per i 4 canali
  confirmation.py      → write_confirmation_mails(...)
  nurturing.py         → write_sequence(...) + write_single(...)
tests/                 → pytest, niente API
```

## Pattern condivisi col resto del team

- Stessa **sidebar** (target audience + brand voice) come negli altri agenti
- Stessa **password gate**
- Stessi **input** condivisi: `context` libero + `references` opzionali
- Stessa funzione `regenerate_one(...)` per rifare una variante con feedback

## Note operative

- I 4 canali Ads vincoli rispettati dal system prompt (max char Google, hook 3s TikTok ecc.). Il rendering UI marca i superamenti con 🔴.
- Per la modalità Nurturing in modo **Sequence**, l'output viene sempre **ordinato per `day` crescente**.
- Tutte le funzioni `write_*` e `regenerate_one` accettano un blocco `context` libero che è il loro grounding principale: meglio rumoroso ma completo che pulito ma povero.
