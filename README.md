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
```bash
uv run alembic upgrade head
```

3. Run the services:

Database:
```bash
docker-compose up -d
```

Ingestion service:
```bash
uv run python -m ingestion.main
```

Feed service:
```bash
uv run uvicorn feed_service.main:app --reload
```

## Client

This exposes a [REST API](http://localhost:8000/docs) at the `/docs` path of the `feed_service`. You'll need to start the database and run `ingestion` for a while to get some content to work with. Obviously the more content you have, the more fun this becomes.

You'll have to create a user first:
```
curl -s -X POST http://localhost:8000/user \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$PALM_USER&password=$PALM_PWD"
```

You can call the feed service using cUrl like this: 
```
# get a token by logging in
ACCESS_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$PALM_USER&password=$PALM_PWD" | jq -r ".access_token")

# Assuming you set the token returned as ACCESS_TOKEN (jq -r ".access_token" does this nicely)
curl -X POST http://localhost:8000/api/feeds -d '["deepseek"]' \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json'

# Use the token to access the feed
curl -X GET http://localhost:8000/api/feeds \
  -H "Authorization: Bearer $ACCESS_TOKEN"

```

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

I estimate about 200GB / week to collect post data as of January 2025, obviously this measures overall Bluesky activity so it can increase.

## References

* [AT Protocol Summary](https://en.wikipedia.org/wiki/AT_Protocol)
* [Jetstream](https://github.com/bluesky-social/jetstream) - simplified version of the Bluesky Firehose that this service uses.

