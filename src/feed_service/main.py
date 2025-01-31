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


class FeedResponse(BaseModel):
    """
    Complete feed response with posts and keywords.
    """

    feed: List[PostResponse]
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


@app.get("/api/feed", response_model=FeedResponse)
async def get_user_feed(
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
        SELECT keyword 
        FROM user_keywords 
        WHERE user_id = :user_id
    """
    )
    result = db.execute(query, {"user_id": current_user_id})
    keywords = [row[0] for row in result]

    if not keywords:
        raise HTTPException(status_code=400, detail="No keywords defined")

    search_terms = " & ".join(keywords)  # TODO | (keyword OR) support
    posts_query = text(
        """
        SELECT id, did, record_text, created_at, reply_parent_uri, reply_root_uri
        FROM posts
        WHERE (created_at < :before) AND
        	(to_tsvector('english', record_text) @@ plainto_tsquery('english', :search_terms))
        ORDER BY created_at DESC
        LIMIT :limit
    """
    )

    before = before or datetime.now(UTC)
    posts = db.execute(posts_query, {"before": before, "search_terms": search_terms, "limit": limit * 2})

    matching_posts = []
    for post in posts:
        if any(keyword.lower() in post.record_text.lower() for keyword in keywords):
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
        if len(matching_posts) >= limit:
            break

    return {"feed": matching_posts, "keywords": keywords}


@app.post("/api/keywords")
async def update_keywords(
    keywords: List[str],
    current_user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the keywords used for filtering a user's feed.

    - **keywords**: List of new keywords to use for filtering
    """
    delete_query = text(
        """
        DELETE FROM user_keywords
        WHERE user_id = :user_id
    """
    )
    db.execute(delete_query, {"user_id": current_user_id})
 
    insert_query = text(
        """
        INSERT INTO user_keywords (user_id, keyword, created_at)
        VALUES (:user_id, :keyword, :created_at)
    """
    )

    for keyword in keywords:
        db.execute(
            insert_query,
            {
                "user_id": current_user_id,
                "keyword": keyword,
                "created_at": datetime.now(UTC),
            },
        )

    db.commit()
    return {"status": "success", "keywords": keywords}


class KeywordResponse(BaseModel):
    id: int
    keyword: str
    created_at: datetime


@app.get("/api/keywords", response_model=List[KeywordResponse])
async def get_user_keywords(
    current_user_id: int = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all keywords for the current user"""
    keywords = db.execute(
        text(
            """
        SELECT id, keyword, created_at
        FROM user_keywords
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """
        ),
        {"user_id": current_user_id},
    ).fetchall()

    return [
        KeywordResponse(
            id=row.id,
            keyword=row.keyword,
            created_at=row.created_at,
        )
        for row in keywords
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
