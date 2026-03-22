# Armenian Voice AI Support Agent

A real-time **voice-powered AI assistant** for Armenian banking information. Speak in Armenian to get details about loans, deposits, and branch locations from three major banks: **ACBA Bank**, **Armeconombank (AEB)**, and **Fast Bank**.

Built with [LiveKit Agents](https://livekit.io/agents) for low-latency audio conversations and browser-based UI for easy testing.

## Features

- **Full Armenian Voice Pipeline**: STT (Whisper via OpenAI/Groq + Silero VAD), LLM reasoning (GPT-4o-mini), TTS (OpenAI)
- **Smart Retrieval Knowledge Base**: Scraped & merged bank data (JSON → context.txt), semantic retrieval with conversation state (remembers your bank/section)
- **Stateful Conversations**: Handles clarifications (\"Which bank?\"), bank switches (with confirmation), follow-ups without repetition
- **Simple Web UI**: One-click connect in browser, live transcripts, no app install needed
- **Data Pipeline**: Selenium scrapers for fresh loans/deposits/branches data
- **Local Docker Setup**: LiveKit server in one command

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Docker
- [OpenAI API key](https://platform.openai.com/api-keys) (or Groq)
- (Optional) Selenium ChromeDriver for scraping

```bash
# 1. Clone & install
git clone <repo> 
cd <repo>
pip install -r requirements.txt

# 2. Copy example env
cp .env .env  # Edit with your API keys
```

### Run Everything
```bash
# Terminal 1: LiveKit server
docker compose up -d

# Terminal 2: Token server (for browser auth)
python token_server.py

# Terminal 3: Voice agent worker
python agent.py

# Terminal 4: Open in browser
# Open frontend/index.html → Click \"Connect\" → Speak!
```

**Example Queries** (in Armenian):
- \"ԱԿԲԱ բանկի վարկերի տոկոսադրույքները\"
- \"Ի՞նչ ավանդներ է առաջարկում Ֆասթ բանկը\"
- \"Արմէկոնոմբանկի Երևանի մասնաճյուղերը\"

## Architecture

```
Browser (index.html + LiveKit Client)
         ↓ WebSocket + Audio
LiveKit Server (docker-compose.yml)
         ↓ Room Events (bank-support)
Agent Worker (agent.py)
  ↓ STT → User Transcript
Knowledge retrieval Pipeline (bank_knowledge.py)
  ↓ Retrieve Chunks → Format Context
LLM (OpenAI/Groq) + Chat History
  ↓ TTS (formatted Armenian/numbers)
Agent Audio → Browser
```

**Data Flow**:
```
scraping/scrapers/*.py (Selenium) → JSON files
                           ↓
scraping/scrapers/merger.py → bank_data/bank_context.txt
                           ↓
Chunks → Vectorized → Query Retrieve → LLM Context
```

## 🛠️ Environment Variables (.env)

```
# STT/LLM/TTS (defaults provided)
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=opt_for_groq_whisper
AGENT_LLM_MODEL=gpt-4o-mini
AGENT_STT_PROVIDER=openai  # or groq
AGENT_TTS_MODEL=tts-1
AGENT_TTS_VOICE=nova

# LiveKit (dev defaults)
LIVEKIT_KEYS=devkey:secret
```

## Update Bank Data

Scrapers fetch live data from bank sites:

```bash
cd scraping
pip install -r scrapers/requirements.txt  # Selenium deps
python scrapers/main.py  # Scrapes all banks
python scrapers/merger.py  # → ../bank_data/bank_context.txt
```

**Supported Data**:
- **Loans**: Rates, max amount, term, prepayment, currency
- **Deposits**: Annual yield, term, min/max amount, currency
- **Branches**: Address

## Supported Banks & Sections

| Bank | Loans | Deposits | Branches |
|------|-------|----------|----------|
| ԱԿԲԱ Բանկ | ✅ | ✅ | ✅ |
| Արմէկոնոմբանկ | ✅ | ✅ | ✅ |
| Ֆասթ Բանկ | ✅ | ✅ | ✅ |


