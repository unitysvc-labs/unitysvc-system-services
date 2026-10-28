# How to use Home

`home` is your account's own files: `{customer_id}/home/` in private UnitySVC
storage. A personal key uses your personal account and a team key uses the
team's; an organization's home belongs to the organization, not to one member.
You share an input with an app by granting it `read` on the folder that holds
it, once, with no per-enrollment copies: two apps granted the same folder read
the same files.

`home` is **experimental**: it is private (not in the catalog) and the Files
pages are behind the experimental flag.

## Grant exactly the folders an app needs

`home` exports `read` and `write` and no `invoke`, so `service:*` and `*` never
reach it. Use an explicit `service:home` grant:

```json
{
  "object": "service:home",
  "permissions": ["read"],
  "options": "path=inputs/datasets/,projects/project-x/"
}
```

| Permission | Operations |
| --- | --- |
| `read` | `list`, `get` |
| `write` | `put`, `post`, `delete` |

`path` lists up to 32 folders, relative to your home, each ending in `/`. A
segment is 1-255 letters, digits, `.`, `_` and `-`, does not start with `.`,
and no folder contains `..`. A
folder covers everything beneath it and nothing beside it: `inputs/` does not
cover `inputs-old/`. A grant without `path` covers nothing. A sole `*` covers
the whole home, only on a key you created yourself and did not bind to an
enrollment; never mix `*` with folders. `write` replaces and deletes files, so
grant it rarely.

## Operations

Every operation is a `POST` to `/home/<op>` with a JSON body; every path is
relative to your home. Answers are `private, no-store` and never cached by
`/m/`.

| Call | Body | Answer |
| --- | --- | --- |
| `POST /home/list` | `{"path": "inputs/", "limit"?: 1–1000, "cursor"?}` | `{"path", "files": [{"path", "size", "last_modified"}], "folders": ["inputs/sub/"], "next_cursor"}` |
| `POST /home/get` | `{"path": "inputs/a.csv"}` | `{"path", "url", "expires_in"}`: GET `url` for the bytes |
| `POST /home/put` | `{"path", "content_type", "size"}` | `{"path", "method": "PUT", "url", "headers", "expires_in"}`: PUT the bytes to `url` with exactly `headers` |
| `POST /home/post` | `{"path", "content_type"?}` | `{"path", "url", "fields", "max_bytes", "expires_in"}`: a browser form upload, `fields` then the file as `file` |
| `POST /home/delete` | `{"path"}` | `{"path", "deleted": true}`, also when there was nothing to delete |

- `list` shows one folder level, at most `limit` entries (default 100), and
  pages with `next_cursor`. Listing a folder above the granted ones shows only
  the folders that lead to them, never a file or an ungranted sibling.
- The bytes never pass through the gateway: `url` is a short-lived presigned
  URL to private storage (a download at most 15 minutes). It is a bearer
  credential until it expires; revoking the key does not recall a URL already
  issued. Downloads are served as attachments.
- One upload is at most the platform's per-object ceiling (1 GiB by default),
  which the signed request enforces.
- File paths: segments of 1-255 characters, no leading or trailing spaces,
  backslashes or control characters, and no `..` or `${` anywhere. Every
  operation accepts exactly the same paths.

| Status | Meaning |
| --- | --- |
| 400 | malformed body or path (`..`, absolute, empty) |
| 403 | the key has no `service:home` grant with the needed permission, or its folders do not cover the path |
| 405 | not a `POST` |
| 413 | `size` over the per-object ceiling |
| 503 | storage or your account context is temporarily unavailable |

`home` is not billed while it is experimental. Storage quotas, copy/move and
richer metadata come later.
