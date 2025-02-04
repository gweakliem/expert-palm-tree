# TODO:

I think what needs to happen next

1. A user needs to be able to have multiple feeds. A feed consists of one or more keywords. 
2. I haven't formally defined how to combine keywords. It would be good to define a way to use AND and OR in keywords. The existing API is more like "key phrase", it will search for phrases if you give it a phrase. Don't bother with FOLLOWING syntax, it's slow and hard to use. What would a more advanced API look like? 

```
    {
        "keywords": ["python & programming"]
    }, 
    {
        "keywords": "python | fastapi"
    }, 
    {
        "keywords": "(python & django) | (fastapi & python)"
    }
```

3. Add a --cursor argument to ingestion so we can start up reading from the past.


## Errors

DB goes down
```
2025-02-02 19:27:33,444 - __main__ - ERROR - Error inserting post 8a859e26-456a-45f3-ad9a-e51b5f9e5cc5: Can't reconnect until invalid transaction is rolled back.  Please rollback() fully before proceeding (Background on this error at: https://sqlalche.me/e/20/8s2b)
```