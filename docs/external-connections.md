# External API connections

Core AI supports two directions. **API keys** lets an external app submit Core AI
jobs and read results. **External connections** lets a Core AI administrator call
a saved HTTPS API or webhook. Each connection defines one endpoint and method.

## Connect and use an external API

1. Open **Connections → External connections → Add external connection**.
2. Choose a platform. Enter the connection name and the endpoint for a single
   operation. Replace placeholders in the endpoint. Enter the token or key only
   in the credential field and save.
3. Select the connection and click **Test connection**. A read test makes a GET.
   A write test checks the route with HEAD and never calls its write method.
   For POST-only webhook endpoints, a HEAD response may be 404 or 405. Test the
   real method with an intentionally configured test workflow and sample input.
4. Click **Fetch preview** for a GET request. Use **View JSON response** to review
   results. To capture a new snapshot for an agent, choose an active project
   and click **Fetch and save**. Select **Open saved source** to check the
   captured data, then select
   that project in Chat or Tasks. For large option chains, open **Snapshot options**
   and select an array such as `data` with a row limit. This preserves the
   upstream ordering and records the applied limit.
5. For POST, PUT, and PATCH, enter the optional JSON body, click **Review and
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
| Corei OS Mini | Dedicated research bearer token; GET /api/research/v1/capabilities | Verify accounts, then create or edit a connection for /api/research/v1/bars. |
| Other HTTPS API | Custom GET, POST, PUT, or PATCH; none, bearer, header, or Basic authentication | Set one endpoint and method for each action. Use n8n for other auth schemes and scheduled or multi-node workflows. |

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

## Upstox data and order execution

1. In Core AI, add an **Upstox · India markets** connection and select the data
   request. Enter the instrument key, expiry, or candle settings when applicable.
   The form builds the HTTPS endpoint. Save the connection with a current Upstox
   access token. A separate connection per recurring request is supported.
2. Test the connection and fetch a preview. Save market data to a project only
   when its membership is appropriate. Keep account, order, and portfolio
   snapshots in an appropriately restricted project.
3. For broker orders, use the **Open Corei OS Mini order desk** link. Sign into
   Corei and open **Execution → Order ticket**. Corei manages its own Upstox
   login, order authorizations, risk checks, release, and reconciliation.
4. Test the ticket with **Paper** first. For a broker order, use a properly
   configured Upstox LIVE account and follow Corei's live controls. Core AI's
   Upstox data token is separate from the Corei order connection.

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
