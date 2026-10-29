# unitysvc-system-services

UnitySVC's **system services**: services the platform answers itself, with no
seller upstream. Each is backed by a reserved upstream scheme that the gateway
resolves on its own:

| Service | Upstream | What the gateway does |
| ------- | -------- | --------------------- |
| `resp200` … `resp503` | `resp://<status>` | returns that status itself; no upstream is contacted |
| `notify` | `notify://user` | delivers a `msg` envelope to the caller's notification preference |
| `ai` | `ai://preference` | rewrites `/ai/...` to the caller's AI preference, or the `service:ai` grant's `service` option, then routes it |
| `me` | `me://user` | projects profile, intents and matching preferences from the routing context within the caller's `service:me` grant; forwards writes to the backend |
| `log` | `log://enrollment` | records entries in the key's activity log (its enrollment's, or the general log) at or above the `service:log` grant's `log_level`; forwards reads to the backend |
| `bill` | `bill://enrollment` | records a charge against the calling key's enrollment and answers a 202 receipt; the platform bills it at the enrollment's service price; `refund` and `query` through the same front door; private, for testing |
| `home` | `home://customer` | forwards file control calls (list, get, put, post, delete) on the customer's home to the backend, which checks the `service:home` grant's folders and answers listings or presigned URLs; experimental, private |
| `storage` | `storage://enrollment` | the same for an enrollment's own folder, resolved from the key's enrollment binding; experimental, private |

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
  shape). For an individual it delivers to their verified address; for a team
  it delivers to the verified addresses of all active members;
- plus, optionally, the account's email preference: an SMTP-input service, such
  as an SMTP relay or an SMTP-to-HTTP converter.

The default mailbox leg ignores the sender's envelope recipients; the chosen
preference controls its own downstream destination. It has no API-gateway interface.
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

`ai` keeps the implicit `invoke` (its `exports` declare no `permissions`, so
`service:*` still reaches it) and exports one option, `service`. A key's
`service:ai` grant can set it to override the preference for that key's calls,
for example to pin an app, or a seller's approved access request, to the AI it
was built for:

```json
{"object": "service:ai", "permissions": ["invoke"], "options": "service=labs/llm-premium"}
```

The value is a catalog service name, never an `a/` alias, `e/` enrollment or
`/ai` itself. The backend checks at issuance that `/ai` can route to it (active,
no enrollment needed, accepts OpenAI chat) and resolves it in place of the
preference, with `X-UnitySVC-AI-Scope: grant`. A grant service that no longer
resolves answers 409; it never falls back to the preference
(unitysvc/unitysvc#2754).

```bash
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"fast","messages":[{"role":"user","content":"Hi"}]}' \
     "$API_GATEWAY_BASE_URL/ai/chat/completions"
```

## Me (`me://user`)

`me` lets a key read, and with permission update, its Customer account's profile,
intents and matching preferences (unitysvc/unitysvc#2720, #2707). `/me` remains
the `/me/profile` alias. Profile paths keep their dotted syntax; `/me/intents`
and `/me/preferences` expose categories of `{text, public, attachments?}` items.
These matching preferences are separate from operational settings.

The service exports exactly `read` and `write`, with no `invoke`. Each grant has
separate `profile`, `intents` and `preferences` options, all defaulting to nothing;
one permission set applies to every selected resource. A granted category reveals
its private/public items and later additions. Absent and ungranted values both
look absent. Request query parameters cannot widen a grant. Broad `service:*` or
`*` never substitutes for the explicit named grant. Currently supported access
uses manually created, unbound keys configured for service access;
enrollment-bound app access is not yet available.

Reads are projected by the gateway from the key-scoped context. Profile writes
merge one section; `POST /me/intents/<category>` and
`POST /me/preferences/<category>` with `{"data":[...]}` replace a whole category,
including items entered by the owner or another app. All service writes lack
publication authority: new/changed public records require an authorized owner
write. Success acknowledges only `{"name":"<category>"}`. `me` is private/no-store,
excluded from `/m/` caching, and unbilled. See the
[service guide](services/specs/me/me-description.md) for shapes, limits, grants,
and attachment references.

```bash
# key policy: {"object": "service:me", "permissions": ["read"], "options": "profile=research,address.state"}
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" "$API_GATEWAY_BASE_URL/me"
# -> {"profile": {"research": {...}}}   (address.state absent if not set)

# key policy: {"object": "service:me", "permissions": ["read"], "options": "intents=travel&preferences=reading"}
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" "$API_GATEWAY_BASE_URL/me/intents/travel"
# -> {"intents": {"travel": [{"text": "Visit Japan next spring.", "public": false}]}}
```

The published grant schema and rendered read-only probes have local contract
tests (also run by the **Me contract** workflow). In an environment containing
`unitysvc-core>=0.2.37,<0.3`, `jinja2`, and `httpx`, run
`python -m unittest discover -s tests -v` alongside the usual
`usvc_seller specs validate` and `usvc_seller specs format --check` checks.
The Bash connectivity probe needs `curl` and Python 3 (standard library only).

## Log (`log://enrollment`)

`log` records what an app did in the calling key's activity log
(unitysvc/unitysvc#2662, #2720, #2780). The key decides which log: a key bound
to an enrollment writes and reads that enrollment's log, an unbound key the
customer's general log. No header names an enrollment (`log` does not read
`X-UnitySVC-Enrollment`). Like `me` it holds the customer's
own data, so its `exports` declare exactly two permissions, `write`
(`POST /`) and `read` (`GET /`), and no `invoke`: `service:*` and `*` never
reach it. Its one option, `log_level` (`debug`, `info`, `warn`, `error`;
default `debug`), is the lowest level a grant records: the gateway drops
entries below it and reports them as `dropped`. Writes are handled by the
gateway end to end (Kafka → ClickHouse); reads are forwarded to the backend,
which lists the same log's entries newest first. `log` is not billed. It is a
full spec under `services/specs/log/`.

```bash
# key policy: {"object": "service:log", "permissions": ["write"], "options": "log_level=info"}
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     -H "Content-Type: application/json" \
     -d '[{"level":"debug","message":"start"},{"level":"info","message":"Checked 214 listings"}]' \
     "$API_GATEWAY_BASE_URL/log"
# -> 202 {"accepted": 1, "dropped": 1, "entry_ids": [...]}
```

<<<<<<< HEAD
## Home and storage (`home://customer`, `storage://enrollment`)

Customer files as two services (unitysvc/unitysvc#2756), both **experimental**:
their listings set `service_options.default_visibility` to `private`, so they
stay out of the catalog, and the Files pages stay behind the experimental flag.

- `home` is the customer's `{customer_id}/home/`. Its `service:home` grant
  names folders with the `path` option (`path=inputs/,projects/x/`, each
  relative and ending in `/`; a sole `*` is the whole home, unbound keys only).
  A customer shares inputs by granting `read` on folders, with no copies.
- `storage` is one enrollment's `{customer_id}/services/{service_id}/{enrollment_id}/`. It has no
  options: a bound key reaches its own enrollment, an unbound key names one with
  `X-UnitySVC-Enrollment`.

Both export `read` (`list`, `get`) and `write` (`put`, `post`, `delete`) and no
`invoke`. Every call is `POST /<service>/<op>` with a JSON body; the gateway
checks the permission and forwards it to the backend, which resolves the
object key from the authenticated key and answers a listing or a short-lived
presigned URL. Bytes move directly between the client and private storage.
Neither service is billed yet.

```bash
# key policy: {"object": "service:home", "permissions": ["read"], "options": "path=inputs/"}
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" -H "Content-Type: application/json" \
     -d '{"path": "inputs/a.csv"}' "$API_GATEWAY_BASE_URL/home/get"
# -> {"path": "inputs/a.csv", "url": "https://…", "expires_in": 900}
=======
## Bill (`bill://enrollment`)

`bill` lets a seller's app charge a customer per use for work delivered outside
the gateway (unitysvc/unitysvc#2744). The caller is a key the customer bound to
one of their enrollments; the charge is billed as `units` of that enrollment's
own service, at its price, and paid to its seller through the ordinary usage
pipeline. `bill` moves money, so its `exports` declare three accounting
permissions and no `invoke`: `charge` (`POST /`), `refund` (`POST /refund`) and
`query` (`GET /`). Only a key bound to an enrollment may hold a `service:bill`
grant, so `service:*`, `*` and a customer's own keys never reach it. Its one
option, `max_units_per_charge`, caps one charge.

The gateway checks the grant, publishes the charge to the usage stream and
answers `202 {"charge_id", "status": "received"}`: that receipt is the only
confirmation, and sellers keep their own records. Billing happens in the usage
consumer shortly after; `GET /bill` lists the enrollment's charges and refunds
with their status. The same `Idempotency-Key` never bills twice. `bill` itself
is free. It is a full spec under `services/specs/bill/`.

```bash
# key bound to the enrollment; policy: {"object": "service:bill", "permissions": ["charge", "query"]}
curl -H "Authorization: Bearer $BILL_KEY" -H "Idempotency-Key: run-6f1c" \
     -H "Content-Type: application/json" \
     -d '{"units": 3, "description": "Run 6f1c"}' "$API_GATEWAY_BASE_URL/bill"
# -> 202 {"charge_id": "...", "status": "received"}
>>>>>>> f8fa3e8 (Add the bill service (bill://enrollment): charge/refund/query exports, 202 receipt)
```

## Repository layout

<<<<<<< HEAD
`notify`, `ai`, `email`, `me`, `log`, `home` and `storage` are full specs (`services/specs/<name>/` with `offering.json`,
=======
`notify`, `ai`, `email`, `me`, `log` and `bill` are full specs (`services/specs/<name>/` with `offering.json`,
>>>>>>> f8fa3e8 (Add the bill service (bill://enrollment): charge/refund/query exports, 202 receipt)
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
