# Signal AI Group Bot

A self-hosted AI assistant for Signal group chats and direct messages. It
keeps the last 10 messages of context per group and answers when someone
starts a message with `@AI`.

It runs on `signal-cli-rest-api` for the Signal side, a FastAPI server for
the bot logic, and OpenRouter for the model (Claude, GPT, Gemini, DeepSeek,
and the rest of the OpenRouter catalog).

## What it does

- Keeps a rolling window of recent group messages, so the model sees who
  said what before it answers.
- Answers only when the trigger prefix (default `@AI`) starts a message.
- Drops stale triggers: a question sent while the host was offline gets
  recorded as context and gets no reply when the bot reconnects.
- Maps raw Signal UUIDs and numbers to friendly names (`Mom`, `Dad`) in the
  context it sends the model.
- Stores Signal keys locally on disk in `./signal-data`. The encryption stays
  on your machine.
- Ships a local simulator, so the prompt handling and context buffer can be
  tested before a number is registered.

## Architecture

```
Signal group members
        |
        v  (Signal protocol, end-to-end encrypted)
signal-cli-api (Docker, port 8080)
  holds the Signal session, decrypts, forwards by webhook
        |
        v  HTTP POST /webhook/signal
signal-ai-bot (FastAPI, port 8000)
  staleness check, rolling group buffer, OpenRouter call, reply dispatch
```

Both services run from `docker-compose.yml`: `signal-cli` and `bot-server`.

## Quickstart

### 1. Configure

```bash
cp .env.example .env
```

Set in `.env`:

- `OPENROUTER_API_KEY`: your OpenRouter API key (openrouter.ai/keys)
- `SIGNAL_PHONE_NUMBER`: the number the bot will register, e.g. `+15551234567`
- `OPENROUTER_MODEL`: model slug, default `anthropic/claude-3.5-sonnet`

### 2. Test without a number (simulation)

Interactive CLI simulator:

```bash
python3 scripts/simulate_chat.py
```

Type messages to build context, then start one with `@AI`.

Or over REST:

```bash
docker compose up bot-server -d

curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"group_id": "family-test", "sender_name": "Mom",
       "message": "@AI what should we make for dinner with chicken and rice?"}'
```

### 3. Register the number

```bash
docker compose up -d signal-cli
python3 scripts/register_number.py
```

The wizard asks for the number, then for the 6-digit SMS code that arrives on
the phone holding the SIM or eSIM. Then start the whole stack:

```bash
docker compose up -d
```

### 4. Add the bot to a group

Add the bot's number as a member of the Signal group. Anyone in the group can
then type `@AI <question>` and the bot replies in the group.

## Configuration

| Variable | Default | What it does |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | (empty) | OpenRouter API key |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | Model slug to query |
| `SIGNAL_PHONE_NUMBER` | (empty) | Registered Signal number, `+1...` format |
| `SIGNAL_API_URL` | `http://localhost:8080` in code; compose sets `http://signal-cli:8080` | Base URL of `signal-cli-rest-api` |
| `TRIGGER_PREFIX` | `@AI` | A message must start with this to get an answer |
| `MAX_CONTEXT_MESSAGES` | `10` | Messages kept per group |
| `STALE_MESSAGE_THRESHOLD_SECONDS` | `120` | Triggers older than this are recorded and not answered |
| `FAMILY_NAME_MAP` | `{}` | JSON map of phone numbers and UUIDs to friendly names |
| `SYSTEM_PROMPT` | see `config.py` | The persona prompt sent with each call |

## Endpoints

- `GET /health`: health and configuration readiness
- `POST /webhook/signal`: ingest endpoint for `signal-cli-rest-api`
- `POST /api/simulate`: run a message through the bot without Signal
- `GET /api/history/{group_id}`: read a group's rolling buffer
- `POST /api/history/{group_id}/clear`: clear a group's buffer

Tests live in `tests/` (`test_api.py` for the endpoints, `test_bot.py` for
the buffer and handler logic) and use fake numbers throughout.
