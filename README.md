# Spring Architecture Assistant & MCP Protocol Inspector (RD-PR01)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Standard%202024--11--05-orange.svg)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced terminal-based (TUI) **Model Context Protocol (MCP) Host** and **Distributed Architecture Assistant** built for the **CC3067 Computer Networks** course at Universidad del Valle de Guatemala (UVG).

It connects Google Gemini (`gemini-2.5-flash` via the modern Interactions API) to multiple local and remote MCP servers over different network transport layers (`stdio` IPC and `HTTP/SSE` on Cloudflare Workers), featuring a real-time split-screen **Network Traffic & Protocol Inspector** monitoring JSON-RPC 2.0 communication packets.

---

## Key Features

- **Split-Screen Terminal User Interface (TUI):**
  - **Left Pane (67%):** Interactive conversational AI assistant powered by Google Gemini.
  - **Right Pane (33%):** Slender live MCP network traffic table (`DataTable`) and JSON-RPC 2.0 packet inspector.
  - **Packet Detail Modal:** Fullscreen detailed packet viewer accessible with `Enter` on any recorded transaction, displaying latency (RTT), packet sizes, transport type, and raw formatted JSON-RPC request and response payloads.
- **Pure Keyboard-Driven Navigation:**
  - `Tab`: Switch focus between chat input and network traffic table.
  - `↑ / ↓`: Scroll and inspect recorded network packets.
  - `Enter`: Expand selected packet into the full inspector modal or send chat message.
  - `/`: Quick slash command auto-complete menu (`/ayuda`, `/herramientas`, `/registro`, `/limpiar`, `/salir`).
  - `Ctrl+C` / `Ctrl+X`: Graceful clean application exit without IDE shortcut conflicts.
- **Multi-Transport MCP Host Architecture:**
  - **Local Subprocesses (`stdio` IPC):** Connects to `spring-architecture-analyzer-mcp`, official Filesystem MCP, and Git MCP via standard input/output pipes.
  - **Remote Edge Server (`HTTP/SSE`):** Connects to `github-spring-profiler-mcp` hosted on Cloudflare Workers edge network.
- **Deterministic Static Architecture Analysis:**
  - Fast AST analysis of Spring Boot Maven projects using Tree-sitter.
  - Dependency graph generation, cycle detection (Tarjan SCC), layer rule enforcement (`Controller -> Service -> Repository`), and refactoring risk ranking.
  - Generates polished dark-mode architectural diagrams saved to local disk with clickable terminal hyperlinks (`file:///...`).
- **Strict Read-Only & Human-in-the-Loop Security:**
  - Analyzer tools are non-destructive and read-only.
  - Risky operations (file writes, git commits) prompt an explicit confirmation modal before sending payloads.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MCP HOST APPLICATION (RD-PR01)                     │
│                                                                             │
│  ┌──────────────────────┐                     ┌──────────────────────────┐  │
│  │   Textual Split TUI  │ ◄─── Event Loop ──► │  Gemini Interactions API │  │
│  │   (Chat + Inspector) │                     │   (gemini-2.5-flash)     │  │
│  └──────────┬───────────┘                     └────────────┬─────────────┘  │
│             │                                              │                │
│             ▼                                              ▼                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │               MCP Client Manager & Protocol Dispatcher                │  │
│  └───────┬──────────────────────┬──────────────────────┬─────────────┬───┘  │
└──────────┼──────────────────────┼──────────────────────┼─────────────┼──────┘
           │ (stdio IPC)          │ (stdio IPC)          │ (stdio IPC) │ (HTTPS JSON-RPC)
           ▼                      ▼                      ▼             ▼
  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ ┌───────────────┐
  │  Filesystem MCP │    │     Git MCP     │    │  Spring Boot │ │ GitHub Remote │
  │ (Official Node) │    │(Official Python)│    │   Analyzer   │ │   Profiler    │
  │     (Local)     │    │     (Local)     │    │ (Local MCP)  │ │ (Cloudflare)  │
  └─────────────────┘    └─────────────────┘    └──────────────┘ └───────────────┘
```

---

## Connected MCP Repositories

| Repository | Scope | Transport | Description |
|---|---|---|---|
| [`RD-PR01`](https://github.com/jcdiegolopez/RD-PR01) | Private | Host | Main console application, TUI, Gemini adapter, client manager, and course deliverables. |
| [`spring-architecture-analyzer-mcp`](https://github.com/jcdiegolopez/spring-architecture-analyzer-mcp) | Public | `stdio` (IPC) | Local Spring Boot AST analyzer, dependency metrics, and dark-mode diagram generator. |
| [`github-spring-profiler-mcp`](https://github.com/jcdiegolopez/github-spring-profiler-mcp) | Public | HTTPS / Edge | Remote Cloudflare Worker inspecting GitHub repositories before local cloning. |

---

## Installation & Setup

### Prerequisites
- **Python 3.10+** (Tested on Python 3.14)
- **Git** installed on PATH
- **Google Gemini API Key** (Free tier available at [Google AI Studio](https://aistudio.google.com/))

### 1. Clone the Repository
```bash
git clone https://github.com/jcdiegolopez/RD-PR01.git
cd RD-PR01
```

### 2. Set Up Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the example environment file and insert your API key:
```powershell
Copy-Item .env.example .env
```
Edit `.env`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
LOG_LEVEL=INFO
```

---

## Running the Application

Launch the split-screen TUI terminal application:
```powershell
python main.py
```

### Keyboard Shortcuts
| Shortcut | Action |
|---|---|
| `Enter` | Send message in chat / Expand selected packet in inspector |
| `Tab` | Switch focus between Chat pane and Network Traffic pane |
| `↑ / ↓` | Navigate through recorded JSON-RPC network packets |
| `/` | Trigger slash command suggestions menu |
| `Ctrl+L` | Clear chat conversation history |
| `Ctrl+C` / `Ctrl+X` | Gracefully quit the application |
| `Esc` | Dismiss modal dialogs |

### Slash Commands
- `/ayuda`: Display command overview and keyboard navigation guide.
- `/herramientas`: List all registered MCP tools and their descriptions.
- `/registro`: Display traffic summary and byte-transfer metrics.
- `/limpiar`: Clear session memory and start fresh context.
- `/salir`: Exit the application.

---

## Running Automated Tests

Run the test suite to verify configuration and MCP client-server communication:
```powershell
python -m pytest
```

---

## Authors & Acknowledgments

- **Author:** Diego López ([@jcdiegolopez](https://github.com/jcdiegolopez))
- **Institution:** Universidad del Valle de Guatemala (UVG)
- **Course:** CC3067 - Computer Networks (Redes)
- **Specification:** Model Context Protocol (Anthropic, 2024-11-05)
