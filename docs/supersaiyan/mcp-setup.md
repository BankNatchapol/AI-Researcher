# Claude Code MCP setup

The AI-Researcher MCP server is read-only and uses stdio. It exposes saved scopes, corpus
status, grounded corpus questions, and parsed paper sections through the same core library as
the `airesearch` CLI.

## Register with Claude Code

Use this repository as the working directory:

```bash
cd /Users/banknatchapol/Desktop/Codes/AI-Researcher
```

Sync the environment, then register the local stdio server:

```bash
uv sync
claude mcp add --transport stdio --scope local ai-researcher -- \
  uv --directory /Users/banknatchapol/Desktop/Codes/AI-Researcher run airesearch mcp
```

The absolute `uv --directory` argument keeps database and `.env` discovery rooted in this
checkout even when Claude Code starts the process from another directory.

To start the same server directly from the repository working directory:

```bash
uv run airesearch mcp
```

Use `claude mcp get ai-researcher` to inspect the saved command or `/mcp` inside Claude Code
to confirm that the server advertises `list_scopes`, `scope_status`, `ask_corpus`, and
`get_paper_sections`.
