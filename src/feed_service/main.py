from fastapi import FastAPI, HTTPException, Depends, Security, APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from datetime import datetime, timedelta, UTC
from pydantic import BaseModel, EmailStr
from shared.config import settings
from shared.database import get_db
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
import logging
from logging.config import dictConfig

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": "feed_service.log",
        },
    },
    "root": {"level": "INFO", "handlers": ["console", "file"]},
}

dictConfig(logging_config)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bluesky Custom Feed API",
    description="API for creating and managing custom Bluesky feeds based on keywords",
    version="1.0.0",
)

# Security configuration
SECRET_KEY = "your-secret-key-here"  # Move to environment variables
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: int


class UserCreate(BaseModel):
    """
    User registration data.
    """

    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class KeywordResponse(BaseModel):
    id: int
    keyword: str
    created_at: datetime


class KeywordUpdate(BaseModel):
    """
    Keywords for filtering posts.
    """

    keywords: List[str]

    class Config:
        json_schema_extra = {"example": {"keywords": ["python", "programming", "tech"]}}


class PostResponse(BaseModel):
    """
    A Bluesky post in the feed.
    """

    id: str
    author: str
    text: str
    created_at: str
    reply_to: str | None
    thread_root: str | None


class FeedListingResponse(BaseModel):
    feed_id: int
    keywords: str
    created_at: datetime
    url: str


class FeedsResponse(BaseModel):
    """
    Response containing list of feeds
    """

    feeds: List[FeedListingResponse]


class FeedResponse(BaseModel):
    """
    Complete feed response with posts and keywords.
    """

    feed: List[PostResponse]
    keywords: List[str]


class FeedCreate(BaseModel):
    """
    Feed creation data.
    """

    keywords: List[str]


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> int:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print(token)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(payload)
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except InvalidTokenError as e:
        print(e)
        raise credentials_exception

    user_query = text("SELECT id FROM users WHERE id = :user_id")
    user = db.execute(user_query, {"user_id": user_id}).first()
    if user is None:
        raise credentials_exception
    return user_id


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


@app.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    query = text(
        """
        SELECT id, password_hash 
        FROM users 
        WHERE email = :email
    """
    )
    result = db.execute(query, {"email": form_data.username}).first()

    if not result or not verify_password(form_data.password, result.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(result.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/users")
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email and password.
    The password will be hashed before storage.
    """
    query = text("SELECT id FROM users WHERE email = :email")
    result = db.execute(query, {"email": user.email}).first()
    if result:
        raise HTTPException(status_code=400, detail="Email already registered")

    insert_query = text(
        """
        INSERT INTO users (email, password_hash, created_at)
        VALUES (:email, :password_hash, :created_at)
        RETURNING id
    """
    )

    result = db.execute(
        insert_query,
        {
            "email": user.email,
            "password_hash": hash_password(user.password),
            "created_at": datetime.now(UTC),
        },
    )
    db.commit()

    user_id = result.first()[0]
    return {"id": user_id, "email": user.email}


@app.get("/api/feeds", response_model=FeedsResponse)
async def list_feeds(
    current_user_id: int = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    List all feeds for the current user.
    """
    query = text(
        """
        SELECT id, created_at
        FROM feeds 
        WHERE user_id = :user_id
    """
    )
    result = db.execute(query, {"user_id": current_user_id})
    feed_listings = result.fetchall()
    print(feed_listings)
    return {
        "feeds": [
            FeedListingResponse(
                feed_id=fl.id,
                keywords="",
                created_at=fl.created_at,
                url=f"/api/feeds/{fl.id}",
            )
            for fl in feed_listings
        ]
    }


@app.get("/api/feeds/{feed_id}", response_model=FeedResponse)
async def get_feed(
    feed_id: int,
    limit: int = 50,
    before: datetime = None,
    current_user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a custom feed for a user based on their keywords.

    - **limit**: Maximum number of posts to return (default: 50)
    - **before**: Only return posts before this timestamp
    """
    query = text(
        """
        SELECT keyword, updated_at 
        FROM user_keywords 
        WHERE user_id = :user_id and feed_id = :feed_id
    """
    )
    result = db.execute(
        query, {"user_id": current_user_id, "feed_id": feed_id}
    )  # Replace with actual user ID
    user_keywords = [row[0] for row in result]

    if len(user_keywords) == 0:
        raise HTTPException(status_code=404, detail="Feed not found")

    search_terms = []
    for idx, keyword in enumerate(user_keywords):
        if keyword.find(" ") != -1:
            search_terms.append(
                f"to_tsvector('english', record_text) @@ phraseto_tsquery('english', :keyword_{idx})"
            )
        else:
            search_terms.append(
                f"to_tsvector('english', record_text) @@ to_tsquery('english', :keyword_{idx})"
            )

    posts_query = text(
        f"""
        SELECT id, did, record_text, created_at, reply_parent_uri, reply_root_uri
        FROM posts
        WHERE (created_at < :before) AND
        ({" AND ".join(search_terms)})
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )

    before = before or datetime.now(UTC)
    params = {"before": before, "limit": limit * 2}
    for idx, keyword in enumerate(user_keywords):
        params[f"keyword_{idx}"] = keyword

    posts = db.execute(posts_query, params)

    matching_posts = []
    for post in posts:
        matching_posts.append(
            {
                "id": post.id,
                "author": post.did,
                "text": post.record_text,
                "created_at": post.created_at.isoformat(),
                "reply_to": post.reply_parent_uri,
                "thread_root": post.reply_root_uri,
            }
        )

    return {"feed": matching_posts, "keywords": user_keywords}


@app.post("/api/feeds")
async def create_feed(
    keywords: List[str],
    current_user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the keywords used for filtering a user's feed.

    - **keywords**: List of new keywords to use for filtering. Keywords may be phrases,
    """
    logger.info(
        f"Creating new feed for user {current_user_id} with keywords: {keywords}"
    )

    insert_feed_query = text(
        """
        INSERT INTO feeds (user_id, created_at, updated_at)
        VALUES (:user_id, :created_at, :updated_at)
        RETURNING id
        """
    )
    insert_keyword_query = text(
        """
        INSERT INTO user_keywords (user_id, keyword, feed_id, created_at)
        VALUES (:user_id, :keyword, :feed_id, :created_at)
    """
    )

    feed = db.execute(
        insert_feed_query,
        {
            "user_id": current_user_id,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    )
    feed_id = feed.first()[0]

    for keyword in keywords:
        db.execute(
            insert_keyword_query,
            {
                "user_id": current_user_id,
                "keyword": keyword,
                "feed_id": feed_id,
                "created_at": datetime.now(UTC),
            },
        )

    db.commit()
    return {"status": "success", "keywords": keywords, "feed_id": feed_id}


@app.delete("/api/feeds/{feed_id}")
def delete_feed(
    feed_id: int,
    current_user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a feed by ID.
    """
    db.begin()
    feed_query = text(
        """
        DELETE
        FROM user_keywords 
        WHERE user_id = :user_id and feed_id = :feed_id
    """
    )
    result = db.execute(feed_query, {"user_id": current_user_id, "feed_id": feed_id})

    query = text(
        """
        DELETE FROM feeds
        WHERE user_id = :user_id and id = :feed_id
    """
    )
    result = db.execute(query, {"user_id": current_user_id, "feed_id": feed_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Feed not found")

    db.commit()
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
