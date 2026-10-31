# How to use Commons

Commons is a free chat room for a group, where each member keeps using their own app. It has no page of its own: you enroll, and the room it creates is in your **Rooms** menu.

## 1. Enroll

Enroll in Commons and approve its one request:

| Request | What it does |
| --- | --- |
| `resource:room`, `create`, `kind=chat&max_members=100` | Creates a `chat` room your account owns when the enrollment activates. The kind and the member cap are fixed; you can't change them while enrolling. |

Each enrollment creates one room. An account can hold up to 10 Commons enrollments at a time.

## 2. Set up your room

Open **Rooms** and choose the new room. As its owner you can:

- rename it and write its description (Markdown);
- choose how long it keeps messages: at most 7 days, or 0 to keep none. Your members' own apps keep whatever history they want;
- create invitation codes, and see and manage its members.

## 3. Invite people

Create an invitation code in the room and send it to the people you want. They redeem it to join, with the role the code offers. A read-only member only receives.

## 4. Post from your own app

Anything that can send a web request can post into the room through its webhook:

```bash
curl -X POST "https://unitysvc.com/v1/rooms/$UNITYSVC_API_KEY/<room handle>" \
  -H "Content-Type: application/json" \
  -d '{"body": "Build 1432 passed"}'
```

- Use an API key with the `api:rooms` write grant. Limit it to this room (`room=<room id>`) so it can post nowhere else.
- `<room handle>` is your own handle for the room, shown in Rooms; the room's id works too.
- The webhook URL with your handle is also shown when you create an API key. On staging, use the staging host instead of `unitysvc.com`.

You can also read and post in the Rooms page itself.

## Cost

Commons and its rooms are free.
