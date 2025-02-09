# TODO:

I think what needs to happen next

1. A user needs to be able to have multiple feeds. A feed consists of one or more keywords. 
2. I haven't formally defined how to combine keywords. It would be good to define a way to use AND and OR in keywords. The existing API is more like "key phrase", it will search for phrases if you give it a phrase. Don't bother with FOLLOWING syntax, it's slow and hard to use. What would a more advanced API look like? 
```
    {
        "keywords": ["python & programming"]
    }, 
    {
        "keywords": ["python | fastapi"]
    }, 
    {
        "keywords": ["(python & django) | (fastapi & python)"]
    }
    One issue here is we have to deal with parsing for validity, we can't just throw them into SQL.
```
3. Add a --cursor argument to ingestion so we can cold start reading from the past, current behavior starts with now. (How useful is reading from past?)
4. After a few days I observed some duplicate posts showing up. For example look at e75a7799-e292-48ed-9da3-f39bc0f4ae62, ecfd8163-032d-4b44-a32c-4209f05be3d1 & dfe19b69-e13e-4eed-8c53-27fd89a2884e, same except for the id and ingest time - clearly we saw the same post at least 3x.
```
SELECT did, commit_rev, commit_rkey, commit_operation, commit_cid, COUNT(*)
FROM posts
GROUP BY did, commit_rev, commit_rkey, commit_operation, commit_cid
HAVING COUNT(*) > 1;
```
5. can I do a "top keywords" monitor? Parse posts, remove stopwords, then feed into a keyword counter.
    1. I think I'd want at least "last day", maybe "last hour", "last week" etc.
    2. how to expire? 
    3. How about phrases? Like "elon musk" how can I track common phrases?


## Optimization

1. Think about how to use ETag - maybe use the latest cursor, since that's a timestamp?
2. Think about how to pre-generate feeds.

## Errors

DB goes down
```
2025-02-02 19:27:33,444 - __main__ - ERROR - Error inserting post 8a859e26-456a-45f3-ad9a-e51b5f9e5cc5: Can't reconnect until invalid transaction is rolled back.  Please rollback() fully before proceeding (Background on this error at: https://sqlalche.me/e/20/8s2b)
```

I see these occasionally - seems to be misidentified Japanese text. Filtered out for now.

```
2025-02-08 12:20:07,861 - __main__ - INFO - record_text contains null byte {'rev': '3lhl4e2vbel26', 'operation': 'create', 'collection': 'app.bsky.feed.post', 'rkey': '3lhl4e2v3j326', 'record': {'$type': 'app.bsky.feed.post', 'createdAt': '2025-02-07T07:48:02.926603+00:00', 'langs': ['en'], 'text': '⤴値上がり高比率銘柄\x00⑤\n(2025/02/07)\n\n日本鋳鉄管(5612)\u30009.18%\nヤマックス(5285)\u30008.84%\n芝浦メカトロニクス(6590)\u30008.49%\n美津濃(8022)\u30008.37%\nオーベクス(3583)\u30008.14%\n'}, 'cid': 'bafyreiajcym4whgydvxhoi5uqzmwv4zhlovcdspcozxd5cw3yy7y6s56h4'}
```

Some other examples it's not clear what this is.
```
2025-02-08 14:21:14,077 - __main__ - INFO - record_text contains null byte {'rev': '3lhldqarice2y', 'operation': 'create', 'collection': 'app.bsky.feed.post', 'rkey': '3lhldqar7j42y', 'record': {'$type': 'app.bsky.feed.post', 'createdAt': '2025-02-07T11:00:07+01:00', 'langs': ['en'], 'text': '🕚 B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g B\x00o\x00n\x00g '}, 'cid': 'bafyreiaxzasrijgosqxtm5r2wivv5mzjqw6plocd5mailzbsacpsrpf47u'}
```


## Monitoring

This query gives you sort of a dashboard:

```
select count(1),min(created_at) as oldest_post,
      max(created_at) as newest_post,
      min(ingest_time) first_ingest, 
      max(ingest_time) as latest_ingest, 
      min(cursor) as min_cursor,
      max(cursor) as max_cursor,
      pg_size_pretty(pg_total_relation_size('"public"."posts"')) as posts_size
from posts ;
```

