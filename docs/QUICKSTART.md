# Quick-starts: connect an AI agent to agentguard

agentguard is a standard MCP (stdio) server. The agent sees five tools and nothing else:
`get_policy`, `check_order`, `place_order`, `get_status`, `audit_tail`. The kill switch and the
policy are **not** agent tools; only the operator controls them.

**Testnet only.** Start in dry-run mode (default). Orders are sent to dYdX testnet only if you
opt in (see "Going live on testnet" below).

Tested: the server starts over stdio and an MCP client lists the tools and calls `place_order`
(verified with the `mcp` Python client). The Claude Code, Cursor and OpenAI Agents SDK snippets
below follow each tool's documented MCP config format but have **not** been run in those
products yet.

## 0. Install and configure (once)
```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dydx]"
python scripts/create_testnet_wallet.py   # writes a TESTNET-only phrase to .env (git-ignored), prints the address
```
Edit `examples/policy.json`: set your limits, and optionally `builder_address` plus
`builder_fee_ppm` (1 to 10,000; 10,000 = 1%) to attach a builder code to every order.

Settings the server reads (environment variables; a `.env` file in the working directory is loaded automatically):

| variable | meaning |
|---|---|
| `AGENTGUARD_POLICY` | path to the policy JSON (default `examples/policy.json`) |
| `AGENTGUARD_ADDRESS` | your TESTNET `dydx1...` address |
| `AGENTGUARD_SUBACCOUNT` | subaccount number, default `0` |
| `AGENTGUARD_AUDIT` | audit log path, default `.agentguard/audit.jsonl` |
| `AGENTGUARD_SUBMITTER` | unset = dry-run; `dydx-testnet` = place real testnet orders |
| `DYDX_TESTNET_MNEMONIC` | signing phrase for the testnet wallet; keep it in `.env`, never in a client config |

Use the **absolute** path to the executable in client configs, for example
`/path/to/agentguard/.venv/bin/agentguard-mcp` (Windows: `D:\path\to\agentguard\.venv\Scripts\agentguard-mcp.exe`).
Set the working directory to the repo (or set `AGENTGUARD_ENV` to the full path of your `.env`).

## 1. Claude Code
```bash
claude mcp add agentguard \
  --env AGENTGUARD_POLICY=/abs/path/agentguard/examples/policy.json \
  --env AGENTGUARD_ADDRESS=dydx1...your-testnet-address \
  --env AGENTGUARD_ENV=/abs/path/agentguard/.env \
  -- /abs/path/agentguard/.venv/bin/agentguard-mcp
```
Then in Claude Code run `/mcp` to confirm it is connected, and ask: *"Use agentguard to check
whether a 0.001 BTC market buy is allowed, then place it."*

## 2. Cursor
Create `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for all projects):
```json
{
  "mcpServers": {
    "agentguard": {
      "command": "/abs/path/agentguard/.venv/bin/agentguard-mcp",
      "env": {
        "AGENTGUARD_POLICY": "/abs/path/agentguard/examples/policy.json",
        "AGENTGUARD_ADDRESS": "dydx1...your-testnet-address",
        "AGENTGUARD_ENV": "/abs/path/agentguard/.env"
      }
    }
  }
}
```
Enable the server under Cursor Settings → MCP, then ask the agent to trade through it.

## 3. OpenAI Agents SDK (Python)
```bash
pip install openai-agents
```
```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    async with MCPServerStdio(params={
        "command": "/abs/path/agentguard/.venv/bin/agentguard-mcp",
        "env": {
            "AGENTGUARD_POLICY": "/abs/path/agentguard/examples/policy.json",
            "AGENTGUARD_ADDRESS": "dydx1...your-testnet-address",
            "AGENTGUARD_ENV": "/abs/path/agentguard/.env",
        },
    }) as guard:
        agent = Agent(
            name="trader",
            instructions="Trade only through agentguard. Always call check_order before place_order "
                         "and explain any rejection to the user. Never try to bypass the guard.",
            mcp_servers=[guard],
        )
        result = await Runner.run(agent, "Buy 0.001 BTC-USD at market, then show my status.")
        print(result.final_output)

asyncio.run(main())
```
(`OPENAI_API_KEY` must be set in your environment for the SDK itself.)

## Operator controls (the human)
```bash
agentguard kill on --reason "volatility"   # blocks every new order on the agent's next call
agentguard kill off
agentguard verify .agentguard/audit.jsonl  # detects any edited or deleted audit line
```

## Going live on testnet
1. Fund the wallet from the testnet faucet (`python scripts/fund_testnet.py <address> 1000`). The faucet credits the
   wallet's **bank balance**, not the trading subaccount, so then deposit it into subaccount 0:
   `python scripts/deposit_to_subaccount.py 1000`, and confirm the subaccount has equity:
   `curl -s https://indexer.v4testnet.dydx.exchange/v4/addresses/<your address>/subaccountNumber/0`
2. Set `AGENTGUARD_SUBMITTER=dydx-testnet` (in `.env` or the client's `env` block).
3. Orders that pass the guard are then signed with `DYDX_TESTNET_MNEMONIC` and broadcast to the
   dYdX testnet with your builder code. Mainnet is refused in the code.

## Rehearse the demo without funds
```bash
python scripts/demo_recording.py --rehearse
```
Uses live testnet prices and a simulated $2,000 account; sends nothing.
