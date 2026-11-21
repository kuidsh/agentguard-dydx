# dYdX Grants application: agentguard, safety rails for AI agents trading on dYdX

> Paste into the form at https://www.dydxgrants.com/grants-application. Fill in the <…> placeholders. Ask in the form which currency grants are paid in (USDC or DYDX).

**Applicant:** David Vega, Mexico (individual). Software and data engineer, 13+ years: Python, AWS, ETL and REST APIs. I've delivered two production Python + blockchain systems, including an election-day integrity system with on-chain/off-chain verification and auditable logging, the same discipline agentguard applies to agent trading.
**Contact:** <email> · **Repo:** <github.com/you/agentguard-dydx> · **Demo video:** <link>
**Category:** Tooling / AI agents (a 2026 priority in the Grants Program update).

## Problem

AI agents can already place orders on dYdX through MCP connectors, but none of the connectors we found documents pre-trade risk limits, an operator kill switch or a tamper-evident record of what the agent did. A bad prompt or a looping agent can open oversized positions in seconds. That keeps careful operators from pointing agents at dYdX, and when it goes wrong it looks bad for dYdX.

## What already works (dYdX testnet, shown in the video)

- An agent connects over MCP (Claude, Cursor, any MCP client) and can only trade through the guard.
- **Allowed order:** a 0.001 BTC order passed the policy, was placed as a stateful order and partially filled on testnet (0.0008 BTC), with our builder code attached and a builder fee of $0.015056. The result is read back from the chain (FILLED / PARTIALLY_FILLED / RESTING / NOT_FILLED).
- **Rejected order:** a 5 BTC order was blocked for 4 policy reasons, before anything was signed.
- **Kill switch:** with the operator kill switch on, every order is blocked. The agent can't turn it off.
- **Audit:** every request, rejection and submission goes to a SHA-256 hash-chained log, and `agentguard verify` confirms it hasn't been changed (9 records, chain intact).
- **Non-custodial:** the operator signs with their own key, and the guard never stores or returns it. Mainnet is refused until review. 44 automated tests.
- Found and fixed a client-side size-rounding issue (0.0003 floored to 0.0002) along the way. We can contribute that fix upstream.

## Milestones (proposed: US$9,000 total)

| # | Deliverable | Weeks | Amount |
|---|---|---|---|
| 1 | Hardening and onboarding: market orders checked at their worst execution price; stateful-order rate limits built into the policy; operator cancel-all and flatten; daily-loss baseline net of deposits and withdrawals; quick-starts for Claude, the OpenAI Agents SDK and LangChain; PyPI package; 3 outside operators running it on testnet | 3 | US$3,000 |
| 2 | Hosted multi-agent mode: per-agent policies, shared kill switch, audit stored in S3 Object Lock, Telegram/webhook alerts, operator status page. Still non-custodial (the guard approves, the agent signs locally) | 4 | US$3,000 |
| 3 | Mainnet beta after an external code review: mainnet enabled behind an explicit operator opt-in, a public usage report (volume routed through builder codes, orders blocked per rule, audit verifications) | 4 | US$3,000 |

## Success metrics

Operators onboarded · volume routed with builder codes · orders blocked by rule · audit verifications run.

## Why it's good for dYdX

It makes dYdX the safest place to point an AI agent: limits, a kill switch and a verifiable record out of the box. Every guarded order carries a builder code, so the volume it brings to dYdX can be measured, and the tool can pay for its own upkeep after the grant.

## License

Apache-2.0 for the guard (public repo).
