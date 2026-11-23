# External API connections

Core AI supports two directions. **API keys** lets an external app submit Core AI
jobs and read results. **External connections** lets a Core AI administrator call
a saved HTTPS API or webhook. Core AI works with direct providers independently
of Corei OS Mini. Only the optional Corei connection talks to Corei.

## Connect and use an external API

1. Open **Connections → External connections → Add external connection**.
2. Choose a platform. Enter the connection name and the endpoint for a single
   operation. Replace placeholders in the endpoint. Enter the token or key only
   in the credential field. On a read connection, use **Add saved request**
   to keep up to 20 named operations on the same HTTPS hostname. The requests
   share one encrypted account credential. Save, then select the operation from
   **Data request** before testing, previewing, or saving.
3. Select the connection and click **Test connection**. This calls the selected
   read operation. The documented Angel One quote and candle reads use POST.
   A write test checks the route with HEAD and never calls its write method.
   For POST-only webhook endpoints, a HEAD response may be 404 or 405. Test the
   real method with an intentionally configured test workflow and sample input.
4. Click **Fetch preview** for a read request. Use **View JSON response** to review
   results. To capture a new snapshot for an agent, choose an active project
   and click **Fetch and save**. Select **Open saved source** to check the
   captured data, then select
   that project in Chat or Tasks. For large option chains, open **Snapshot options**
   and select an array such as `data` with a row limit. This preserves the
   upstream ordering and records the applied limit.
5. For a custom write or webhook, enter the optional JSON body, click **Review and
   send**, then **Confirm and send**. Core AI does not retry these requests
   automatically. Configure idempotency in the receiving workflow if a resend is
   possible. For an ambiguous timeout, check upstream activity before sending again.
6. Use **Recent requests** to view outcome, status, and duration. Use **Edit
   connection** to pause or replace a credential. Responses and secrets are
   excluded from request history. A move to another endpoint path or
   authentication mode requires credential re-entry. Saved credentials are
   encrypted with the workstation key and cannot be revealed by this panel.

Connections call public HTTPS on port 443, validate the destination IP and
hostname, and do not follow redirects. Responses must be JSON when present;
the request and response are size-bounded. A project snapshot includes its
provider, path, retrieval time, and redacted payload. Use approved sources
when adding imported responses to projects shared with other users.

## Platform recipes

| Platform | Connect from Core AI | Workflow |
|---|---|---|
| n8n | Production Webhook URL; POST; match the Webhook node's header name and key | Active n8n Webhook → validate JSON → process → return JSON. Send an explicit request from Core AI. |
| Instagram | Instagram professional account token; GET the media endpoint on graph.instagram.com | Fetch authorized media. Use an n8n workflow for provider webhook processing or publishing after approval. |
| Facebook | Page token; GET the Page's posts endpoint on graph.facebook.com | Fetch authorized Page posts. Use an n8n workflow for write operations that need Meta approval. |
| WhatsApp | WhatsApp Business token; GET the phone-number metadata endpoint | Verify the authorized business number. Use n8n's WhatsApp trigger/actions for incoming messages and approved replies. |
| Twelve Data | API key in Authorization; GET /time_series | Start with EUR/USD, 1h, and 50 rows. Set symbols and intervals according to the provider plan. |
| Upstox | Current OAuth bearer token; choose an Upstox data request | Use V3 quotes, OHLC, Greeks and candles, options chain and contracts, or account data such as orders, trades, positions, holdings, and funds. |
| Zerodha | Kite API key and current access token | Start with the profile. Add quotes, candles, holdings, positions, margins, orders or trades as needed. |
| Angel One | SmartAPI API key and current JWT; workstation IP and MAC settings | Start with the profile. Add positions, holdings, funds and order or trade books. Add quotes or candles with the documented JSON body. |
| MT5 EA | Public HTTPS bridge URL and bearer token | Fetch account or market data exposed by your bridge. Alternatively, submit selected data from an EA to the Core AI job API. |
| Corei OS Mini | Dedicated research bearer token; GET /api/research/v1/capabilities | Verify the v1 research contract and authorized accounts. Add saved bars requests referencing those accounts. |
| Other HTTPS API | Custom GET, POST, PUT, or PATCH; none, bearer, header, or Basic authentication | Save additional reads on the same host or save one endpoint per write action. Use n8n for other auth schemes and scheduled or multi-node workflows. |

Meta examples require the Graph API version and app/account permissions you use.
Core AI accepts provider-issued tokens. Configure OAuth login, token refresh,
native event signatures, and scheduled execution in the provider or n8n as
applicable.

- [n8n HTTP Request credentials](https://docs.n8n.io/integrations/builtin/credentials/httprequest/)
- [Instagram platform documentation](https://developers.facebook.com/docs/instagram/platform/instagram-api/changelog/)
- [Meta WhatsApp Cloud API](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api)
- [Twelve Data API](https://twelvedata.com/docs)
- [Upstox authentication](https://upstox.com/developer/api-documentation/authentication/)
- [Upstox option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/)

## Independent providers and optional Corei synchronization

- **Upstox** runs directly from Core AI with a current OAuth access token. Use
  your Upstox app to obtain the token, then rotate it in the saved Core AI
  connection. Enter the raw token without the Bearer prefix.
- **Zerodha** runs directly with the Kite app API key and session access token.
  Generate the session in your Kite login integration. The API secret is used
  for generating the session there. Rotate just the access token in Core AI.
- **Angel One** runs directly with the SmartAPI app API key and JWT from
  your SmartAPI login. Set `CORE_AI_ANGEL_LOCAL_IP`,
  `CORE_AI_ANGEL_PUBLIC_IP` and `CORE_AI_ANGEL_MAC` in the
  `core-ai-api` systemd service environment to match your actual workstation
  network identity. Enter the raw JWT. Add the full endpoint for quotes or candles
  under **Additional saved requests**. For a quote, the JSON body is shaped like
  `{"mode":"FULL","exchangeTokens":{"NSE":["<instrument-token>"]}}`.
- **MT5** requires an already-running bridge if Core AI is to fetch data from
  it. If your EA calls Core AI directly, allow the Core AI HTTPS origin under
  **Tools → Options → Expert Advisors** and use a scoped Core AI job key.
- **Corei OS Mini** stays optional. Configure its dedicated research credential,
  open its Core AI connection, then fetch **Capabilities** to see allowed account
  IDs. Add a named request to the same connection for
  `/api/research/v1/bars?account_id=<account-uuid>&symbol=EURUSD&timeframe=H1&limit=100`.
  Each fetch reads the current stored bars from Corei. Saved project snapshots
  represent the response at fetch time. Both products keep independent logins and
  credentials, and this integration does not synchronize orders or portfolios.

These broker presets collect data. The Upstox task workflow also supports a manually confirmed live DAY limit order, described below. Use each broker's own order workflow, the optional Corei
order desk, or an explicitly configured external action endpoint with its own
approval and reconciliation controls.

- [Kite Connect authentication](https://kite.trade/docs/connect/v3/user/)
- [Angel One SmartAPI reference](https://smartapi.angelone.in/docs)
- [MT5 EA WebRequest](https://www.mql5.com/en/docs/network/webrequest)

## n8n or another app → Core AI

1. In **Connections → API keys**, create a key with job submission and result
   access. Limit its model, project and agent to the workflow's purpose.
2. In n8n, store the Core AI key as a Bearer Auth credential. Use an approved
   trigger such as Schedule, Instagram/WhatsApp, or a verified webhook. Validate
   and select the fields you need. Keep credentials out of AI prompts and JSON logs.
3. Add an HTTP Request node with POST to
   `https://ai.coreeye.in/api/v1/automation/jobs` and a JSON body such as
   `{"request_id":"stable-source-event-id","prompt":"Summarize the supplied event data."}`.
   Use the actual provider event ID when available. Include a model only when the
   Core AI key needs the caller to choose one.
4. Save the returned job ID. Use a Wait and bounded polling loop with GET to
   `https://ai.coreeye.in/api/v1/automation/jobs/{id}`, or use Core AI's signed
   job-completion webhook and fetch the result upon receipt. Stop on terminal state.
5. Route results to review, notification, or storage. For messages or publishes,
   validate the recipient and apply your existing approval/consent workflow.
   Market-data workflows are for analysis. Order execution stays in its broker
   or trading platform.

## Connect to Corei OS Mini

Enable its optional read API first. In the server's private
`/etc/corei-os-mini/workstation.env` set:

```dotenv
COREI_RESEARCH_API_TOKEN=<dedicated random credential of 32 or more characters>
COREI_RESEARCH_API_ACCOUNTS=<comma-separated Corei account UUIDs>
```

Restart `corei-os-mini-workstation` after editing the existing file. Add a
**Corei OS Mini** connection in Core AI, then test and preview **capabilities**.
Use one of its account IDs and the broker symbol stored by Corei. An H1 example
endpoint is:

```text
https://corei-os-mini.coreeye.in/api/research/v1/bars?account_id=<uuid>&symbol=EURUSD&timeframe=H1&limit=50
```

Use the same private credential in the Core AI credential field. This endpoint
returns collected bars only for the listed accounts. Run **Fetch and save** to
make the snapshot available to an agent.

## Upstox trading task in Core AI

1. Import or create skills and assign them to the master agent and any specialist agents.
2. Save an Upstox connection. Supply the app API key and secret together, and optionally a current access token. To exchange a single-use code obtained through your registered app login, open **Authorize Upstox app**, enter the exact registered redirect URL and code, and complete the exchange.
3. Open **Broker analysis task and live order** on the saved connection. Select a project and master agent, enter the instrument keys and the task objective. Select specialist agents and additional saved datasets as required. Full quotes use the instrument list. Additional datasets use their saved instrument, expiry, or date parameters.
4. Start collection. Keep the task ID. Click **Review task result** to check progress and queue the master synthesis after the specialist runs finish. Review again to read the final output. Agents use their assigned skills.
5. For an intended live trade, enter the account ID, instrument, side, product, quantity and price. Review the explicit confirmation. Each task accepts one submission per instrument. Check broker status and fills after submission. A timeout requires reconciliation before further action. Account eligibility and the broker's order controls determine acceptance.
