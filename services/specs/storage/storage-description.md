# How to use Storage

`storage` is an enrollment's own folder of files:
`{customer_id}/services/{service_id}/{enrollment_id}/`
in private UnitySVC storage, so all your files sit under your account, grouped
by service, then enrollment. The app you enrolled keeps its working files and
results there; you can read them back. Paths in calls are always relative to
the enrollment's folder (`results/out.json`). Inputs you want to share with the app
belong in your `home` instead, granted by folder.

`storage` is **experimental**: it is private (not in the catalog) and the Files
pages are behind the experimental flag.

## Grant

`storage` exports `read` and `write` and no `invoke`, so `service:*` and `*`
never reach it. It has **no options**: which folder a key reaches is never
chosen by its policy.

```json
{"object": "service:storage", "permissions": ["read", "write"]}
```

| Permission | Operations |
| --- | --- |
| `read` | `list`, `get` |
| `write` | `put`, `post`, `delete` |

Which enrollment:

- A key **bound to an enrollment** reaches only that enrollment's folder.
  Naming another enrollment with `X-UnitySVC-Enrollment`, even another
  enrollment of the same service, is refused (403).
- Your **own unbound key** names the enrollment with the
  `X-UnitySVC-Enrollment: <code>` header, and reaches only enrollments it may
  see (your team's shared enrollments and your own personal ones); any other
  code is 404.

## Operations

The same five operations as `home`, each a `POST` to `/storage/<op>` with a
JSON body; every path is relative to the enrollment's folder. Answers are
`private, no-store` and never cached by `/m/`.

| Call | Body | Answer |
| --- | --- | --- |
| `POST /storage/list` | `{"path": "results/", "limit"?: 1–1000, "cursor"?}` | `{"path", "files": [{"path", "size", "last_modified"}], "folders", "next_cursor"}` |
| `POST /storage/get` | `{"path": "results/out.json"}` | `{"path", "url", "expires_in"}`: GET `url` for the bytes |
| `POST /storage/put` | `{"path", "content_type", "size"}` | `{"path", "method": "PUT", "url", "headers", "expires_in"}`: PUT the bytes to `url` with exactly `headers` |
| `POST /storage/post` | `{"path", "content_type"?}` | `{"path", "url", "fields", "max_bytes", "expires_in"}`: a browser form upload |
| `POST /storage/delete` | `{"path"}` | `{"path", "deleted": true}` |

The bytes never pass through the gateway: `url` is a short-lived presigned URL
to private storage (a download at most 15 minutes) and a bearer credential
until it expires. A cancelled or expired enrollment's key gets no new URLs; one
already issued lasts until it expires. One upload is at most the platform's
per-object ceiling (1 GiB by default).

| Status | Meaning |
| --- | --- |
| 400 | malformed body or path, or an unbound key without `X-UnitySVC-Enrollment` |
| 403 | no `service:storage` grant with the needed permission, or a bound key naming another enrollment |
| 404 | an enrollment this key may not see |
| 405 | not a `POST` |
| 413 | `size` over the per-object ceiling |
| 503 | storage or your account context is temporarily unavailable |

`storage` is not billed while it is experimental. Quotas, retention after
cancellation and storage billing come later.
