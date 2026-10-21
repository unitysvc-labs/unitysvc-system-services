# System services

- `notify/` — full spec; `notify://user` delivers to the caller's notification preference.
- `ai/` — full spec; `ai://preference` rewrites `/ai/...` to the caller's AI preference.
- `resp*.json` — param files rendered through `../templates/resp/`, described below.

## Direct-response (`resp://`) services

This folder holds **direct-response** services under `unitysvc/`. Each one
returns a fixed HTTP status code straight from the UnitySVC gateway — no real
upstream is ever contacted.

They are backed by the reserved `resp://<status>` upstream scheme
(unitysvc/unitysvc#1188): when the gateway sees `base_url = "resp://<status>"`
it synthesizes the response itself and closes the request loop, instead of
proxying. The synthetic response still flows through the normal pipeline, so it
composes with the logging (`/l/`), failover (`/f/`), and tee (`/t/`) primitives.

## Service overview

| Service   | Returns | Use                                                          |
| --------- | ------- | ------------------------------------------------------------ |
| `resp200` | 200     | success sink — "do nothing, just close the loop" (e.g. `/l/resp200`) |
| `resp400` | 400     | client-error negative-path testing                          |
| `resp404` | 404     | client-error negative-path testing                          |
| `resp429` | 429     | rate-limit / backoff / retry testing                        |
| `resp500` | 500     | failing primary for `/f/` failover testing                  |
| `resp503` | 503     | failing primary for `/f/` failover testing                  |

## How each service is defined

- **offering.json** — `upstream_access_config.direct_response.base_url` is
  `resp://<status>`. That is the whole trick: the gateway recognizes the
  `resp://` scheme and produces the response without an upstream hop.
- **listing.json** — a free (`list_price: 0`) listing whose gateway path is
  `${API_GATEWAY_BASE_URL}/resp<status>`. The connectivity test is shared from
  `unitysvc/docs/connectivity.sh.j2`.

## Connectivity test

All services share one test, `docs/connectivity.sh.j2`, which has two modes:

- **Local / upstream** (`usvc_seller data run-tests`): there is no upstream to
  reach, so the test passes immediately ("returns success directly").
- **Gateway** (`usvc_seller services run-tests`): curls the gateway and asserts
  it returns **exactly** the requested status. A `resp503` service is healthy
  when the gateway returns 503, so the test compares against the expected code
  (read from `resp://<status>` at render time) rather than a 2xx range.
