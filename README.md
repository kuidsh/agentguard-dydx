# agentguard: guardrails for AI agents trading on dYdX

**Status: v0.2 in progress (2026-11-18). Testnet only.** 61 offline tests pass. Testnet order placement with builder codes is implemented and verified live on 2026-11-19: a real order through the guard filled on testnet with the builder fee recorded on the fills. Runs as an MCP server, so
Claude, Cursor, the OpenAI Agents SDK, LangChain and other MCP clients can use it.

AI agents can already trade on dYdX v4. Existing MCP connectors either expose order placement
with no documented risk controls, or are read-only analytics (e.g. `dydx-agent-gateway`).
agentguard sits between the agent and the exchange:

- **Policy the agent can't change:** allowed markets and order types, max order, position and
  gross notional, max leverage, a daily loss limit net of deposits and withdrawals (then closing
  orders only), max limit-price deviation from the oracle, market orders sized and capped at their
  worst execution price, minimum free collateral and an orders-per-minute limit.
- **Operator kill switch:** `agentguard kill on` blocks every new order immediately. It isn't an
  agent tool.
- **Tamper-evident audit log:** every request, rejection (with reasons) and submission goes to a
  SHA-256 hash-chained JSONL file. `agentguard verify` detects any edited or deleted line. In
  hosted mode it's stored in S3 Object Lock.
- **Builder code:** optionally adds a dYdX builder code (`fee_ppm`, max 10,000 = 1%) to every
  order that passes. This is how the tool earns. No governance vote is needed.
- **Non-custodial:** the operator signs with their own key. agentguard never stores, logs or
  returns keys, and mainnet is refused in the code.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                      # 61 offline tests
agentguard demo                # offline walkthrough: 1 allowed order, 4 rejected
agentguard verify .agentguard/demo-audit.jsonl
```

### Use it from Claude Desktop / Claude Code (testnet data, dry-run orders)
```json
{"mcpServers": {"agentguard": {
  "command": "agentguard-mcp",
  "env": {"AGENTGUARD_POLICY": "/abs/path/examples/policy.json",
          "AGENTGUARD_ADDRESS": "dydx1...your TESTNET address"}}}}
```
More: [docs/QUICKSTART.md](docs/QUICKSTART.md) has setup for Claude Code, Cursor and the OpenAI Agents SDK,
how to go live on testnet, and `python scripts/demo_recording.py --rehearse` for a dry-run demo.

Agent tools: `get_policy`, `check_order`, `place_order`, `get_status`, `audit_tail`.
Operator: `agentguard kill on --reason "..."` / `agentguard kill off`.

## Layout
| file | role |
|---|---|
| `agentguard/policy.py` | policy schema and validation (builder fee cap, network) |
| `agentguard/guard.py` | pure pre-trade checks → allow/deny with reasons |
| `agentguard/audit.py` | hash-chained audit log + `verify` |
| `agentguard/indexer.py` | read-only dYdX Indexer client (testnet default); day-start equity from `/historical-pnl` |
| `agentguard/service.py` | ties it together: rate limit, kill switch, logging |
| `agentguard/executor.py` | dry-run submitter; dYdX testnet submitter with builder code (opt-in) |
| `agentguard/mcp_server.py` | MCP tool surface |
| `scripts/` | testnet wallet, faucet, fixture capture and demo-recording helpers |
| `docs/QUICKSTART.md` | connect Claude Code, Cursor or the OpenAI Agents SDK |
| `infra/template.yaml` | hosted mode (Lambda + DynamoDB + S3 Object Lock), not deployed |

## Roadmap
- **v0.2 (in progress):** done: testnet order placement through `dydx-v4-client` with the builder
  code (reached the chain; funded live fill pending), day-start equity from `/historical-pnl`,
  market-data fixtures from the live Indexer. Pending: account and PnL fixtures and a confirmed
  builder fee on a real fill, both of which need a funded testnet subaccount.
- **v0.2.1:** daily-loss baseline net of deposits/withdrawals (`/transfers`); market orders checked
  and sent at their worst execution price (`max_market_slippage_bps`).
- **v0.3:** hosted multi-agent mode (`infra/`), operator dashboard, per-agent policies, alerts (Telegram/email).
- **v1.0:** mainnet release after an external review and a written legal opinion. LangChain and
  OpenAI Agents SDK examples.

See `COSTS.md`, `PROPOSAL.md` (dYdX Grants draft) and `docs/JURISDICTION.md`.
Not financial advice. Trading perpetuals is high risk. License: Apache-2.0.
