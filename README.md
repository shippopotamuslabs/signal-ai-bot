# 🤖 Signal AI Group Bot

A self-hosted, lightweight AI assistant for Signal group chats and direct messages. It listens to conversations, remembers the last 10 messages of group context, and responds whenever someone starts a message with `@AI`.

Powered by **`signal-cli-rest-api`**, **FastAPI**, and **OpenRouter** (supports Claude 3.5 Sonnet, GPT-4o, Gemini 2.5, DeepSeek, etc.).

---

## 🌟 Key Features

- **Context-Aware**: Retains a rolling window of recent group chat messages so the AI understands who said what.
- **Trigger-Based**: Only generates responses when `@AI` (or your configured trigger) is at the start of a message.
- **Staleness Protection**: Ignores old questions sent while your computer was closed or offline (preventing spam upon reconnection).
- **Friendly Name Mapping**: Maps raw Signal UUIDs / numbers into friendly names (e.g. `Mom`, `Dad`, `Alex`) for natural AI context.
- **E2EE Privacy**: Cryptographic keys are saved locally on your disk in `./signal-data`.
- **Local Simulation**: Includes a built-in interactive simulator and `/api/simulate` endpoint to test before your eSIM arrives.

---

## 📁 Architecture Overview

```
[ Signal Group Members ]
          │
          ▼ (E2EE Signal Protocol)
┌──────────────────────────────────────────────┐
│ Docker Compose                               │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ signal-cli-api (Port 8080)             │  │
│  │ - Maintains persistent Signal session  │  │
│  │ - Decrypts & forwards via Webhook      │  │
│  └───────────────────┬────────────────────┘  │
│                      │ HTTP POST Webhook     │
│                      ▼                       │
│  ┌────────────────────────────────────────┐  │
│  │ signal-ai-bot (FastAPI / Port 8000)    │  │
│  │ - Ingestion & Staleness check          │  │
│  │ - Rolling group buffer (last 10 msgs)  │  │
│  │ - OpenRouter API (LLM generation)      │  │
│  │ - Dispatches reply to Signal group     │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## 🚀 Quickstart

### 1. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and set:
- `OPENROUTER_API_KEY`: Your OpenRouter API key (get one at [openrouter.ai/keys](https://openrouter.ai/keys))
- `SIGNAL_PHONE_NUMBER`: The phone number you will register (e.g., `+15551234567`)
- `OPENROUTER_MODEL`: Desired model (default: `anthropic/claude-3.5-sonnet`)

---

### 2. Testing Without eSIM or Signal (Local Simulation)

You can test the bot's prompt handling, context buffer, and OpenRouter integration immediately:

**Option A: Interactive CLI Simulator**
```bash
python3 scripts/simulate_chat.py
```
Type messages to build context, and start a message with `@AI` to see the bot answer!

**Option B: REST API Simulation**
```bash
# Start the bot server
docker compose up bot-server -d

# Send a simulated message
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "group_id": "family-test",
    "sender_name": "Mom",
    "message": "@AI what should we make for dinner with chicken and rice?"
  }'
```

---

### 3. Registering Your Phone Number (When eSIM arrives)

1. **Start the Signal API daemon:**
   ```bash
   docker compose up -d signal-cli
   ```

2. **Run the interactive registration wizard:**
   ```bash
   python3 scripts/register_number.py
   ```
   - Enter your phone number (e.g. `+12345678900`).
   - You will receive a 6-digit SMS code on the phone where the eSIM is installed.
   - Enter the code in the terminal.

3. **Start the full bot:**
   ```bash
   docker compose up -d
   ```

---

### 4. Adding Bot to Your Family Signal Group

1. In the Signal app on your phone, open your Family Group.
2. Tap the group name > **Add Members** > Select or enter your bot's phone number.
3. Once added, anyone in the group can type:
   > `@AI what's a good movie to watch tonight?`
4. The bot will reply directly into the group!

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | `""` | OpenRouter API Key |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | Model slug to query |
| `SIGNAL_PHONE_NUMBER` | `""` | Registered phone number (`+1...`) |
| `SIGNAL_API_URL` | `http://signal-cli:8080` | URL of `signal-cli-rest-api` |
| `TRIGGER_PREFIX` | `@AI` | Word required at start of message |
| `MAX_CONTEXT_MESSAGES` | `10` | Number of recent messages retained per group |
| `STALE_MESSAGE_THRESHOLD_SECONDS` | `120` | Max age in seconds for @AI triggers |
| `FAMILY_NAME_MAP` | `{}` | JSON map of phone numbers / UUIDs to friendly names |

---

## 🛠️ Management & API Endpoints

- `GET /health`: Health status & configuration readiness check.
- `GET /api/history/{group_id}`: View recent rolling chat memory for a group.
- `POST /api/history/{group_id}/clear`: Clear the memory buffer for a group.
- `POST /webhook/signal`: Ingest webhook endpoint for `signal-cli-rest-api`.
