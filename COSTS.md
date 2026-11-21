# Cost and revenue model

## Starting investment (non-AWS)
| item | cost |
|---|---|
| dYdX Grants application | US$0 |
| Testnet funds | US$0 (faucet; a step for the user) |
| Domain (optional) | ≈ US$12 a year |
| **Total** | **US$0–12** |

## AWS per month
| mode | services | estimate |
|---|---|---|
| Local (v0.1–v0.2): runs beside the agent | none | **US$0** |
| Hosted (v0.3), ~100k guard calls a month | Lambda arm64 256 MB × 0.3 s ≈ 7.5k GB-s (inside the 400k GB-s free tier) + 0.1M requests ($0.02) | ≈ US$0.02 |
| | DynamoDB on-demand, ~300k reads/writes | ≈ US$0.50 *(rate not re-verified)* |
| | S3 Object Lock audit, < 1 GB | ≈ US$0.10 |
| | CloudWatch Logs, 30-day retention | ≈ US$0.50 |
| | **Total hosted** | **≈ US$1–3** |

Lambda's $0.0000166667/GB-s, $0.20 per 1M requests and free tier come from the AWS Lambda
pricing page (read 2026-11-16). The other rates are standard published prices, not re-read today.
The mx-central-1 region may price slightly differently from us-east-1.

## Revenue
1. **dYdX grant (near term).** Rolling applications, with a first response in about 1 week. The draft
   asks for US$9,000 in 3 milestones (≈ US$3,000 each); see PROPOSAL.md. Grant sizes aren't
   published. Comparable data points are a US$3,000 integration grant and monthly retainers of
   US$6–14k. *Estimate.*
2. **Builder fee (recurring).** A builder fee on every fill that passes the guard. At 300 ppm (0.03%):
   - US$100 a month needs ≈ US$333k of monthly volume through the guard
   - one agent trading US$20k a day ≈ US$600k a month ≈ US$180 a month
3. **Hosted plan (later).** Optional subscription for teams that don't want to self-host
   (e.g. US$29 a month per agent). Not validated.

## Payback
The start cost is US$0, so payback comes with the first grant milestone, or about 2 active
agents' builder fees covering hosted AWS. Milestone 1 (testnet placement + live state) is about
3–4 weeks of work.

## Validation (success test)
SUCCESS = a dYdX grant approved (milestone 1 paid), **or** 3+ external operators running it on
testnet with builder codes, plus a written commitment from one of them to use it on mainnet.
