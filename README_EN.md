<p align="center">
  <img src="assets/icon.svg" width="80" height="96" alt="Kiro Proxy">
</p>

<h1 align="center">Kiro Proxy for Claude Code</h1>

<p align="center">
  Reverse proxy connecting Kiro IDE's free Claude API to Claude Code
</p>

---

> **✅ Verified Status (2026-04-03)**
>
> Verified: **Claude Code** — tool calling, streaming, and Context Window HUD all work correctly.
>
> Unverified: Codex CLI, Gemini CLI (code support exists but not tested)

## What's Changed

Based on [petehsu/KiroProxy](https://github.com/petehsu/KiroProxy), with the following changes for Claude Code:

### Bug Fixes
- **Fixed SSE streaming event format** — Original proxy only sent `data:` lines, missing the required `event:` line. Claude Code uses `event:` to identify event types; without it, `message_start` is never received, triggering a non-streaming fallback that sends the same request twice (double token usage)
- **Fixed non-streaming response content loss** — Wrong key used to extract response content (`result["text"]` → `result["content"]`)
- **Fixed Flow state not persisted** — `complete_flow`/`fail_flow` updated in-memory state but never wrote to SQLite; WebUI showed "pending" after refresh

### New Features
- **Context Window HUD** — Estimates tokens from system + messages + tools, fills SSE `usage` field so Claude Code's context progress bar works
- **SQLite flow persistence** — All request records saved to `flows.db`, survives restarts
- **HTTP proxy support** — Configure outbound proxy via env vars to speed up AWS requests
- **WebUI request inspector** — Modal showing system_prompt, messages, tools, response content, token usage with collapsible JSON tree
- **No retries, no smart summarization** — Proxy is pure passthrough; all intelligent behavior delegated to Claude Code

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/xavier66/kiro-proxy-for-claude-code.git
cd kiro-proxy-for-claude-code

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Get a Kiro Token

**Option A: Scan local token (if you have Kiro IDE)**

1. Open Kiro IDE and make sure you're logged in
2. Start the proxy, open WebUI → Accounts → Scan Tokens

**Option B: Online login**

1. Start the proxy, open WebUI → Accounts → Online Login
2. Choose Google / GitHub / AWS Builder ID and complete authorization

### 3. Start the Proxy

```bash
# Default port 8080
python run.py

# Custom port
python run.py 8081

# With outbound proxy (optional, speeds up AWS access)
KIRO_PROXY_ENABLED=true KIRO_PROXY_URL=http://127.0.0.1:7897 python run.py 8081
```

Open http://localhost:8081 for the WebUI.

### 4. Configure Claude Code

Add a custom API provider in Claude Code:

```
API Provider: Anthropic
API Key:      any
Base URL:     http://localhost:8081
Model:        claude-sonnet-4-6
```

Or via environment variables:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8081
export ANTHROPIC_API_KEY=any
claude
```

### 5. Verify

Send a message. The WebUI Flows tab should show a completed request, and Claude Code's Context Window HUD should display a non-zero value.

---

## Model Mapping

Claude Code model names are automatically mapped to Kiro API names:

| Claude Code Model | Kiro API Model |
|-------------------|----------------|
| `claude-sonnet-4-6` | `claude-sonnet-4.6` |
| `claude-opus-4-6` | `claude-opus-4.6` |
| `claude-haiku-4-5-20251001` | `claude-haiku-4.5` |
| Any unknown model | `claude-sonnet-4.6` (default) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KIRO_PROXY_ENABLED` | `false` | Enable outbound proxy |
| `KIRO_PROXY_URL` | `http://127.0.0.1:7897` | Outbound proxy address |

---

## WebUI

Visit http://localhost:8081 to access:

- **Flows** — All request records with full detail modal (system prompt, messages, tools, response, token usage)
- **Accounts** — Add/manage Kiro accounts, view token status
- **Monitor** — Request stats, latency, error rate
- **Settings** — Rate limiting config

---

## Other Clients (Unverified)

Code-level support exists but has not been tested:

**Codex CLI**
```bash
export OPENAI_API_KEY=any
export OPENAI_BASE_URL=http://localhost:8081/v1
codex
```

**Gemini CLI**
```bash
export GEMINI_API_BASE=http://localhost:8081/v1
```

---

## Account Management CLI

```bash
python run.py accounts list
python run.py accounts scan --auto
python run.py accounts add
python run.py accounts export -o acc.json
python run.py accounts import acc.json
python run.py login google
python run.py login github
```

---

## Disclaimer

This project is for educational purposes only. Commercial use is prohibited. Any consequences from using this project are the user's responsibility.

This project is not affiliated with Kiro / AWS / Anthropic.

---

Based on [petehsu/KiroProxy](https://github.com/petehsu/KiroProxy)
