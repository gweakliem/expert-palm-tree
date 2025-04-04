# 👩‍💻🌴

A custom feed generator for Bluesky that allows users to create personalized feeds based on keywords and topics.

## Setup

1. Create a .env file with your configuration.
```
DATABASE_URL=postgresql://user:password@localhost/bluesky_feed
BATCH_SIZE=250
FLUSH_INTERVAL_SECONDS=5
```

2. Initialize the database:

Start the database:
```bash
docker-compose up -d
```

And run the migrations to get the database setup
```bash
uv run alembic upgrade head
```


3. Run the services:

Ingestion service:
```bash
uv run python -m ingestion.main
```

Feed service Web API:
```bash
uv run uvicorn feed_service.main:app --reload
```

Embedding Service:
```bash
uv run python -m embedding.main
```

## Web API

This exposes a [REST API](http://localhost:8000/docs) at the `/docs` path of the `feed_service`. You'll need to start the database and run `ingestion` for a while to get some content to work with. Obviously the more content you have, the more fun this becomes.

You'll have to create a user first:
```
curl -X 'POST' \
  'http://127.0.0.1:8000/api/users' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "email": "user@example.com",
  "password": "verysecure"
}'
```

Now obtain an access token (assuming you have PALM_USER and PALM_PWD exported):
```
# get a token by logging in
ACCESS_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$PALM_USER&password=$PALM_PWD" | jq -r ".access_token")
```

You can now call the feed service using cUrl like this, assuming you set the token returned as ACCESS_TOKEN

```
curl -i -X POST http://localhost:8000/api/feeds -d '["deepseek"]' \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json'
```

And now you can get your feed, assuming FEED_ID is the id returned above:

```
curl -i -X GET http://localhost:8000/api/feeds/$FEED_ID \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Feed construction

Feeds are composed of keywords, which should probably be called "key phrases". For example creating a feed with the keywords `["trump administration","venezuela"]`, will find posts that match the phrase "trump administration" and contain the word "venezuela". A post that mentions "the administration of Donald Trump" and also mentions Venezuela will _not_ show up in this feed.

The feed is composed using the logical `AND` of the phrases, so all phrases must be matched to show up in the feed. I might add `OR` at a later date but I feel like this is not that valuable for the purpose of building a feed, you could logically just build 2 feeds and look at both of them to get the same results as an `OR`.

## Architecture

```mermaid
flowchart LR
    JS[Bluesky Firehose\nJetstream] --> Ingest[Ingestion Service\nFastAPI]
    Ingest --> PostDB[(Post Database\nTimescaleDB)]
    Ingest --> Cache[(Redis Cache)]

    PostDB --> API[API Service\nFastAPI]
    Cache --> API

    API --> WebApp[Vue Frontend]

    UserDB[(User Database\nPostgres)] --> API

    subgraph "User Interaction"
        WebApp --> Auth[Authentication]
        WebApp --> Keywords[Keyword Management]
        WebApp --> Feed[Custom Feed View]
    end
```


## Performance

I estimate about 50GB / day to collect post data as of February 2025, obviously this measures overall Bluesky activity so it can increase if Bluesky becomes more popular and active.

## References

* [AT Protocol Summary](https://en.wikipedia.org/wiki/AT_Protocol)
* [Jetstream](https://github.com/bluesky-social/jetstream) - simplified version of the Bluesky Firehose that this service uses.

[Resolve Bluesky Handle to DID](https://tools.simonwillison.net/bluesky-resolve) is a useful tool.
[PDSls](https://pdsls.dev/at/did:plc:mqne6vqaz2flizfdszbqcvv6) similar tool for DID lookup.
