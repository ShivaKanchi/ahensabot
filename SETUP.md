# nanobot Setup Guide

## Current Docker Setup (Quick Start)

Purpose: quick instructions for running `nanobot` in Docker — copyable and agent-friendly.

### Prerequisites

- Docker & Docker Compose installed
- Ensure `./nanobot/config.json` exists and `./workspace/` is present

### Using Ollama (Recommended - Local LLM)

**Setup:**
```bash
# 1. Make sure Ollama is running on your host machine
ollama serve

# 2. From project root, start nanobot
docker-compose up -d
```

**Verify:**
```bash
# View logs
docker-compose logs -f nanobot

# Check status inside container
docker-compose exec nanobot nanobot status
```

**Run commands:**
```bash
# Send single message
docker-compose exec nanobot nanobot agent -m "Hello"

# Interactive chat
docker-compose exec -it nanobot nanobot agent

# Run gateway (for chat channel integrations)
docker-compose exec nanobot nanobot gateway

# Check available commands
docker-compose exec nanobot nanobot --help

# View logs anytime
docker-compose logs -f nanobot

# Stop and remove
docker-compose down
```

**Configuration:**
- Model: `ollama/gemma3:12b` (configured in `config.json`)
- API Base: `http://host.docker.internal:11434` (configured in `config.json`)
- No API key required ✅
- Container auto-connects to host Ollama server

### Using OpenRouter (Alternative - Cloud LLM)

If you prefer cloud-based LLM instead of local Ollama:

**Setup:**
```bash
# 1. Get API key from https://openrouter.ai/keys
# 2. Create or edit .env file in project root
echo "OPENROUTER_API_KEY=sk-or-v1-your-actual-key" >> .env

# 3. Update NANOBOT_MODEL in docker-compose.yml or .env
export NANOBOT_MODEL=openrouter/anthropic/claude-opus-4-5

# 4. Start nanobot
docker-compose up -d
```

**Run commands:**
```bash
# View logs
docker-compose logs -f nanobot

# Send single message
docker-compose exec nanobot nanobot agent -m "Hello"

# Interactive chat
docker-compose exec -it nanobot nanobot agent

# Stop container
docker-compose down
```

### Paths and Mounts (host -> container)

- `./nanobot/config.json` -> `/root/.nanobot/config.json`
- `./workspace` -> `/root/.nanobot/workspace`
- Port `18790` exposed (host:container)

### Notes

- For Ollama: keep `ollama serve` running on host while Docker container is active
- For OpenRouter: ensure `.env` has `OPENROUTER_API_KEY` before `docker-compose up`
- To persist config changes, edit `./nanobot/config.json` on host
- View logs anytime with: `docker-compose logs -f nanobot`

---

## 🐳 Running nanobot on Docker (Detailed Guide)

This guide explains how to run nanobot using Docker and Docker Compose.

### Prerequisites

- Docker installed ([download here](https://www.docker.com/products/docker-desktop))
- Docker Compose installed (included with Docker Desktop)
- For Ollama: [Ollama installed](https://ollama.ai) on your host machine
- For cloud LLM: Your API keys ready (OpenRouter, OpenAI, etc.)

### Quick Start with Docker Compose

#### Using Ollama (Local LLM - Recommended)

**Step 1: Start Ollama on your host machine**
```bash
# On Windows/Mac/Linux host (not in Docker)
ollama serve
# This starts Ollama server on localhost:11434
```

**Step 2: Run nanobot in Docker**
```bash
# From project root
docker-compose up -d
```

This will:
- ✅ Build the Docker image (first time only)
- ✅ Start nanobot container
- ✅ Create persistent volumes for config and workspace
- ✅ Expose port 18790 for the gateway
- ✅ Auto-connect to Ollama via `host.docker.internal:11434`

**Step 3: Verify it's working**
```bash
# Check logs for any errors
docker-compose logs -f nanobot

# Test with a single message
docker-compose exec nanobot nanobot agent -m "Hello, what's your name?"

# Check status
docker-compose exec nanobot nanobot status
```

#### Using Cloud LLM (OpenRouter, OpenAI, etc.)

**Step 1: Set up Environment Variables**

Copy the `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your:
- **LLM API Key** (at least one): OpenRouter, OpenAI, Anthropic, etc.
- **Chat Channel Tokens** (optional): Telegram, Discord, Slack, etc.

Example `.env`:
```
OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here
NANOBOT_MODEL=openrouter/anthropic/claude-opus-4-5
TELEGRAM_BOT_TOKEN=your-bot-token-here
```

**Step 2: Run with Docker Compose**

**Build and start the container:**
```bash
docker-compose up -d
```

**View logs:**
```bash
docker-compose logs -f nanobot
```

**Stop the container:**
```bash
docker-compose down
```

---

### Alternative: Build and Run Manually

If you prefer not to use Docker Compose:

**Build the image:**
```bash
docker build -t nanobot:latest .
```

**Run the container with Ollama:**
```bash
docker run -d \
  --name nanobot \
  --restart unless-stopped \
  # nanobot Setup Guide

  This file explains how to run nanobot locally (recommended via Docker Compose), how I'm running the server on my machine, and common configuration and troubleshooting steps.

  ## Quick Run — how to start (short)

  1. Start a local Ollama server on the host (host machine, not inside the container):

  ```bash
  ollama serve
  ```

  2. From project root, build and start nanobot:

  ```bash
  docker-compose up -d --build
  ```

  3. Verify and run a quick test:

  ```bash
  docker-compose exec nanobot nanobot status
  docker-compose exec nanobot nanobot agent -m "Hello"
  docker-compose logs -f nanobot
  ```

  ## How I'm running the server now (my setup)

  - I run `ollama serve` on the host so the Ollama API is available at `http://localhost:11434`.
  - Container connects to the host Ollama via `host.docker.internal:11434` (Docker Desktop on Windows/macOS).
  - I set provider env vars in `docker-compose.yml` so the container uses the host endpoint, e.g.:

  ```yaml
  environment:
    NANOBOT_AGENTS__DEFAULTS__MODEL: ${NANOBOT_MODEL:-ollama/gemma3:12b}
    NANOBOT_PROVIDERS__OLLAMA__API_KEY: "none"
    NANOBOT_PROVIDERS__OLLAMA__API_BASE: "http://host.docker.internal:11434"
    NANOBOT_PROVIDERS__VLLM__API_KEY: "test-vllm-key"   # optional, for vLLM testing
    NANOBOT_PROVIDERS__VLLM__API_BASE: "http://host.docker.internal:11434"
  ```

  - The container in this repo runs with `entrypoint: ["tail","-f","/dev/null"]` so you can `exec` into it and run `nanobot` commands interactively (or remove/override entrypoint to run the gateway).

  ## Configuration overview

  - Main config: `nanobot/config.json` (mounted to `/root/.nanobot/config.json` in the container).
  - Default model is configured under `agents.defaults.model` (default: `ollama/gemma3:12b`).
  - Provider connection endpoints live under `providers` (e.g. `providers.ollama.apiBase`).

  Example `providers.vllm` snippet in `config.json`:

  ```json
  "vllm": {
    "apiKey": "your-vllm-key",
    "apiBase": "http://host.docker.internal:11434",
    "extraHeaders": null
  }
  ```

  ## Test / debug steps

  - Check `nanobot` status inside the container:

  ```bash
  docker-compose exec nanobot nanobot status
  ```

  - If a request fails, view recent logs:

  ```bash
  docker-compose logs --tail 200 -f nanobot
  ```

  - From inside the container, verify you can reach the Ollama/vLLM endpoint:

  ```bash
  docker-compose exec nanobot curl -sS http://host.docker.internal:11434/api/tags
  ```

  If curl fails, ensure `ollama serve` is running on the host and Docker can resolve `host.docker.internal`. On Linux, set `extra_hosts: ["host.docker.internal:host-gateway"]` in `docker-compose.yml`.

  ## Using cloud providers instead of local Ollama

  - Create a `.env` with your cloud provider keys (example):

  ```bash
  OPENROUTER_API_KEY=sk-or-...
  NANOBOT_MODEL=openrouter/anthropic/claude-opus-4-5
  ```

  - Then run:

  ```bash
  docker-compose up -d --build
  ```

  And verify with `docker-compose exec nanobot nanobot status`.

  ## Troubleshooting (common issues)

  - Error: Cannot connect to host localhost:11434 — start `ollama serve` on the host and/or point `apiBase` to `host.docker.internal:11434`.
  - If provider shows `not set` in `nanobot status`, confirm env vars or `config.json` entries are present and the container was restarted.
  - API keys: ensure your `.env` contains the correct values and restart the container after editing.

  ## Useful commands reference

  ```bash
  # Start Ollama on host
  ollama serve

  # Build and run
  docker-compose up -d --build

  # Check container status
  docker-compose ps

  # Check nanobot status
  docker-compose exec nanobot nanobot status

  # Send a single message
  docker-compose exec nanobot nanobot agent -m "Hello"

  # Start interactive chat
  docker-compose exec -it nanobot nanobot agent

  # View logs
  docker-compose logs -f nanobot

  # Stop and remove
  docker-compose down
  ```

  ## Paths & mounts

  - `./nanobot/config.json` -> `/root/.nanobot/config.json` (persisted)
  - `./workspace` -> `/root/.nanobot/workspace`
  - Port `18790` exposed for the gateway

  ---

  If you'd like, I can also:

  - Add a short `.env.example` file for common env vars, or
  - Add a one-line script `run-local.sh` that starts Ollama (if installed) and the container.

  Updated file: [SETUP.md](SETUP.md)
```yaml
