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

3. 