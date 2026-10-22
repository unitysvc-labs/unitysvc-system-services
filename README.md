# unitysvc-system-services

UnitySVC's **system services**: services the platform answers itself, with no
seller upstream. Each is backed by a reserved upstream scheme that the gateway
resolves on its own:

| Service | Upstream | What the gateway does |
| ------- | -------- | --------------------- |
| `resp200` … `resp503` | `resp://<status>` | returns that status itself; no upstream is contacted |
| `notify` | `notify://user` | delivers a `msg` envelope to the caller's notification preference |
| `ai` | `ai://preference` | rewrites `/ai/...` to the caller's AI preference, then routes it |

This repository was `unitysvc-services-resp`; `notify` moved here from
`unitysvc/unitysvc-services-notify`, which keeps the `msg-to-*` / `*-relay`
delivery services.

## Direct response (`resp://`)

### Why this exists

Every UnitySVC service requires an `upstream_access_interface`, so historically
there was no way to model a "do nothing, just close the loop" endpoint. The
reserved `resp://<status>` upstream scheme (unitysvc/unitysvc#1188) fills that
gap: `base_url = "resp://200"` is a valid, resolvable upstream that means
"the gateway itself produces a 200 response." The synthetic response still runs
through the normal pipeline, so it composes with the wrapper primitives.

### Services

| Service   | Returns | Typical use                                   |
| --------- | ------- | --------------------------------------------- |
| `resp200` | 200     | success sink / no-upstream logging            |
| `resp400` | 400     | client-error negative-path testing            |
| `resp404` | 404     | client-error negative-path testing            |
| `resp429` | 429     | rate-limit / retry-backoff testing            |
| `resp500` | 500     | failing primary for failover testing          |
| `resp503` | 503     | failing primary for failover testing          |

### How they are used

Reach a direct-response service like any other gateway service, optionally
wrapped by a primitive:

```bash
# Direct: the gateway returns 200 with no upstream hop.
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     "$API_GATEWAY_BASE_URL/resp200"

# Logging-as-a-service: log the request, then close the loop with a 200.
# The /l/ wrapper records the request + the synthesized 200 even though
# there is no upstream to forward to — the headline use case (#1129).
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     "$API_GATEWAY_BASE_URL/l/resp200"

# Failover: use resp503 as a guaranteed-failing primary to exercise the
# fall-over path — the gateway returns 503, /f/ treats that as a failure
# and serves the _else target instead.
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     "$API_GATEWAY_BASE_URL/f/resp503?_else=p/openai"

# Tee: mirror a copy of a real request to a resp200 sink (the sink just
# swallows the mirrored call and returns 200; _to names the tee target).
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     "$API_GATEWAY_BASE_URL/t/p/openai?_to=resp200"
```

Because the response is produced inside the normal gateway path, `/l/` logs it,
`/f/` can fall over from it, and `/t/` can mirror to it.

Direct-response services compose naturally with the primitives: `/l/resp200`
(log a request with no real upstream) is the headline case, `resp5xx` makes a
guaranteed-failing `/f/` primary, and `resp200` makes a `/t/` sink. A bare
`/resp200` is useful too — as a gateway placeholder while a real upstream is
being wired up, and as a lightweight health check that exercises the full
auth + routing path without touching any upstream.

## Notify (`notify://user`)

`notify` takes a `msg` envelope over the API gateway and delivers it to the
caller's platform notifications plus the external destination set as their
notification preference (unitysvc/unitysvc#1526). It has no SMTP interface:
email goes through the SMTP gateway's separate `email` service
(unitysvc/unitysvc#2678). It is a full spec under
`services/specs/notify/`, published under the `labs` provider as before.

## Email (SMTP username `email`)

`email` is the SMTP counterpart of `notify` (unitysvc/unitysvc#2678). A caller
sends a message to the SMTP gateway with AUTH username `email`, and the backend
resolves it as an implicit `/b/` group:

- this service, whose upstream is the platform mail server with
  `to: ${ customer_secrets.__PRIMARY_USER_EMAIL }` (the `smtp-to-mailbox`
  shape), so it delivers to the caller's verified address;
- plus, optionally, the account's email preference: one SMTP service that
  delivers to its own recipient, such as `smtp-relay` with `SMTP_RELAY_TO` or
  an enrolled `smtp-relay`.

Every leg delivers only to the recipient its upstream pins; the message's own
`To`/`Cc`/`Bcc` never widen the recipients. It has no API-gateway interface.
The `SVCPASS_SMTP_*` seller secrets are the ones `smtp-to-mailbox` uses (same
seller). The spec stays `draft` until the backend and smtp-gateway support
lands.

## AI (`ai://preference`)

`ai` answers an OpenAI chat request with the caller's AI preference: a `/p/llm`
tier or other LLM service by its name (`labs/llm-balanced`), or an alias
(unitysvc/unitysvc#2659). Services that require enrollment, including `e/<code>`
enrollments, are refused. A service is one model, so no model is stored beside
it. The routing context carries the resolved
preference, and the gateway rewrites `/ai/...` to it the way it rewrites an
`/a/<name>` alias. With no preference, `/ai` uses `labs/llm-balanced`; a team
key uses the team's preference, never a member's. `ai` is free; each call is
billed by the service it resolves to. A preference that no longer resolves
answers 409. It is a full spec under
`services/specs/ai/`.

```bash
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"fast","messages":[{"role":"user","content":"Hi"}]}' \
     "$API_GATEWAY_BASE_URL/ai/chat/completions"
```

## Repository layout

`notify` and `ai` are full specs (`services/specs/<name>/` with `offering.json`,
`listing.json`, `provider.json` and their docs). The six `resp` services are
nearly identical — they differ only in an HTTP `status`, a
`label`, and a one-line `blurb` — so they're authored as **param files** rendered
through one shared template, not six copies of `offering.json` + `listing.json`
(see [unitysvc-sellers#90](https://github.com/unitysvc/unitysvc-sellers/pull/90)).

```
services/templates/resp/                   # one parameterized template for all six
  provider.json                   # static provider metadata
  offering.json.j2                # {{ status }} {{ label }} {{ blurb }}
  listing.json.j2                 # {{ status }} {{ label }} → connectivity.sh.j2
  connectivity.sh.j2              # shared connectivity test (local + gateway)
services/specs/unitysvc/
  resp200.json                    # { "template": "resp", "parameters": { "status": 200, "label": "OK", … } }
  resp200.service.json            # backend service_id (sidecar; committed)
  resp400.json … resp503.json     # + their .service.json sidecars
```

The generated `offering.json` / `listing.json` are **never committed** — they're
rendered in memory from the param file + template each time `specs` runs. Only
the param files, their sidecars, and the template are tracked.

## Local development

```bash
pip install "unitysvc-sellers>=0.2.4"      # param-file rendering

# Validate schemas + file references (renders each param file first)
usvc_seller specs validate

# Check / apply formatting (alphabetical keys, 2-space indent)
usvc_seller specs format --check
usvc_seller specs format

# Run the connectivity tests against the upstream (resp:// → passes directly)
usvc_seller specs run-tests
```
