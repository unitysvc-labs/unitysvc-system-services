# How to use Me

`me` exposes information owned by the Customer account bound to your key. A
personal key uses the personal Customer; a team key uses that team. Team members
share the account's information: **private** means unpublished outside the
account except through explicit grants, not hidden from other account members.

| Resource | Meaning | Example category or path |
| --- | --- | --- |
| `profile` | Descriptive facts | `research`, `address.state` |
| `intents` | What the customer wants to do next | `needs`, `buy`, `sell`, `travel` |
| `preferences` | Matching tastes, constraints and recurring choices | `reading`, `tools`, `general` |

Categories are suggestions, not an enum. Preferences can say “I like science
fiction, but absolutely hate horror” without separate like/dislike fields.
Operational **settings**, such as notification routing or AI selection, remain
separate and are not exposed at `/me/settings`. A statement records information;
it does not place an order, authorize contact, publish a seller listing, or start
a matching job.

## Grant exactly what an app needs

Use an explicit `service:me` grant. For example:

```json
{
  "object": "service:me",
  "permissions": ["read", "write"],
  "options": "intents=travel,needs&preferences=reading,tools"
}
```

The option string belongs to the key policy, not the request URL. `profile`,
`intents`, and `preferences` are independent selectors; an omitted selector
defaults to `[]` and shares nothing from that resource. Profile keeps its dotted
path syntax. Intents and preferences use flat names matching
`^[a-z][a-z0-9_-]{0,63}$`, with up to 64 distinct names per option. For example,
use `book-needs`, not `needs.books`. Nested categories and item-index grants are
unsupported.

The grant's **one permission set applies to all selected resources**. The
example authorizes both read and write on every listed category. It cannot
express profile-read-only plus intents-write-only in one grant. Use only
`["read"]` for reading or `["write"]` for replacement without reading.

A read grant reveals **all private and public items** in its selected categories,
including items added later. A public flag never expands the grant. A write
grant can replace the entire selected list, including items entered by the owner
or another app; it does not mean “edit only this app's items.” Obtain read
authority and read first if preserving existing items matters.

A manually created, unbound key may use a resource's sole selector `*`, such as
`intents=*`, to include all its current and future categories. Never combine `*`
with names. Enrollment-bound/delegated policies must name categories and cannot
use `profile=*`, `intents=*`, or `preferences=*`.

`me` exports `read` and `write`, with no `invoke`. Broad `service:*` or `*`
authority does not substitute for an explicit `service:me` grant. Currently
supported access uses manually created, unbound keys configured for service
access. Enrollment-bound app access is not yet available; acceptance of a grant
at key issuance does not itself enable that access.

## Read a resource or category

```bash
curl -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     "$API_GATEWAY_BASE_URL/me/intents/travel"
```

```json
{
  "intents": {
    "travel": [
      {"text": "Visit Japan next spring.", "public": false}
    ]
  }
}
```

| Request | Result |
| --- | --- |
| `GET /me` or `GET /me/profile` | Existing granted profile projection; never an aggregate of all resources |
| `GET /me/profile/<path>` | One existing profile path, within the profile grant |
| `GET /me/intents` | All allowed, present intents categories under `{"intents": {...}}` |
| `GET /me/intents/travel` | Only the allowed travel category under the same wrapper |
| `GET /me/preferences` | All allowed, present preferences categories under `{"preferences": {...}}` |
| `GET /me/preferences/reading` | Only the allowed reading category under the same wrapper |

An unset category, an ungranted category, and a key without read permission all
produce an empty resource object, such as `{"intents":{}}`. An allowed category
stored as an empty list remains `{"intents":{"travel":[]}}`. Service responses
omit document versions and sibling-category metadata. Query parameters cannot
widen the projection. Unknown resources and deeper paths return 404;
unsupported methods return 405.

## Replace a category

```bash
curl -X POST -H "Authorization: Bearer $UNITYSVC_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"data":[{"text":"Visit Japan next spring.","public":false}]}' \
     "$API_GATEWAY_BASE_URL/me/intents/travel"
# 200 {"name":"travel"}
```

Use `POST /me/preferences/reading` with the same body shape for preferences.
Each write replaces exactly one complete list and preserves sibling categories
and the other resource. `{"data":[]}` clears a category while keeping its name.
Posting to `/me/intents` or `/me/preferences` without a category returns 405.

The backend independently verifies the key's write/category grant and account
edit authority. Owners and billing managers may edit; a read-only account member
cannot gain edit authority merely by using a write-granted key. A concurrent
save can return a generic 409. Read again and reconcile deliberately if you have
read permission; do not blindly retry a stale replacement. Successful writes
return only `{"name":"<category>"}`, even with a write-only key: no stored
items, version, item counts or sibling names are returned.

**Service writes cannot publish new or changed public records**, including
writes made with manual keys. They may add/change private items, remove items,
and preserve already-public records exactly as stored. Changing the text or
attachment metadata of a public item requires owner publication through the
owner editor. Duplicate public records cannot be introduced by copying one
existing record. Only an authorized owner API write can publish new content.

Existing profile writes stay compatible: `POST /me` or `POST /me/profile` with
`{"name":"research","data":{"topic":"Compilers"}}` merges that section and
acknowledges `{"name":"research"}`. Do not send a profile publication flag
through the service API.

## Item shape and limits

```json
{
  "text": "Use this itinerary as background for planning.",
  "public": false,
  "attachments": [
    {
      "url": "https://example.com/itinerary.pdf",
      "name": "Itinerary",
      "media_type": "application/pdf"
    }
  ]
}
```

Every item requires nonblank string `text`. `public` is a strict boolean,
defaults to `false`, and is always returned explicitly. `attachments` is an
optional list. An attachment requires an absolute HTTP(S) `url`; `name` and
`media_type` are optional. Unknown fields, null items/lists, and values such as
`"public":"false"` are invalid. Authored text, list order, duplicate statements,
false flags and empty arrays are preserved. Omitted and empty attachment lists
are equivalent when comparing a public record.

| Limit | Maximum |
| --- | --- |
| Categories per resource | 64 |
| Items per category / per resource | 128 / 512 |
| Text per item | 8 KiB of UTF-8 |
| Attachments per item | 8 |
| URL / attachment name / media type | 2,048 / 200 / 100 characters |
| Complete stored document, including version metadata | 64 KiB of compact UTF-8 JSON per resource |

Attachment links are metadata only. UnitySVC does not fetch, upload, extract or
embed these files. Use stable references rather than short-lived signed links.
The file's access policy remains independent: marking an item public never
changes file permissions, and receiving a URL does not guarantee download
access. No anonymous public-content endpoint is added by these fields.

## Privacy and caching

Reads and writes are private/no-store and unbilled. The gateway refreshes the
key-scoped routing context after owner or service changes. `/m/` caching is
disabled for every `me://` resource, including alias/enrollment routes.

## Connectivity test

The supplied Bash connectivity probe requires `curl` and Python 3. It uses only
Python's standard library to validate the three JSON resource wrappers, and
reads without changing account data. Set `UNITYSVC_API_KEY` before running it;
a missing or invalid key produces an authentication failure.

The implementation design and related repositories are tracked in
[unitysvc#2707](https://github.com/unitysvc/unitysvc/issues/2707).
