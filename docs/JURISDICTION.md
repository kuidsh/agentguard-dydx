# Where to base agentguard: Ecuador, Mexico or USA

*Research notes, 2026-11-17. Not legal advice. Get a written opinion before mainnet.*

| | USA | Ecuador (B2B entity) | Mexico (David) |
|---|---|---|---|
| dYdX access | **Excluded.** dYdX services aren't available to US residents or US-incorporated entities, and the US is on dYdX's restricted list | Not on the named restricted list (US, Canada, UK, sanctioned countries) | Not on the named restricted list |
| Receiving the grant / builder fees (likely USDC) | n/a | **Risky.** Crypto isn't an authorized means of payment, and BCE said it will refer use of crypto as payment to the Fiscalía (Aug 2024); a stricter reform was proposed. New SRI crypto reporting starts with FY2026 (resolution NAC-DGERCGC26-038, 4 Nov 2026) | **Allowed.** Banxico's limits apply to financial institutions, not individuals. Income is taxable in MXN at receipt; RESICO vs actividad empresarial to be confirmed with a contador |
| Selling the software | possible, but no dYdX product | fine if billed in USD fiat | fine; CFDI for MX clients, export invoice for foreign ones |
| Regulatory exposure of the tool | n/a | low if non-custodial | low if non-custodial and self-hosted by the operator; **a public hosted trading front-end could touch Ley Fintech/CNBV rules**, so get an opinion before v0.3 hosted mode |

## Recommendation
- **Grant applicant and builder-code address: David, in Mexico.**
- **Ecuador B2B:** can subcontract fiat-paid work (AWS ops) to David, but shouldn't hold the USDC revenue.
- **USA:** not used for this product. Hosting: AWS mx-central-1 (Mexico) or sa-east-1, not US regions.
- **Product rules:** non-custodial (the operator signs with their own key), self-hosted by default,
  operators must confirm they aren't in a dYdX-restricted country, and no custody of user funds.

Sources: dYdX geo-restrictions (help.dydx.trade/en/articles/166970), dYdX Foundation Dec 2025 grants update,
Primicias 15 Aug 2024 (BCE reform), El Comercio 16 Nov 2026 (SRI resolution), Siempre al Día (SAT treatment).
