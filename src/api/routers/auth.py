"""Authentication routes for QuickPulse V2."""

from datetime import datetime, timedelta, timezone
import hmac
import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from src.api.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# If AUTH_SECRET_KEY is not set or still the insecure default, generate a random
# session-scoped key. Tokens won't persist across restarts (users just re-login),
# but the app is safe from token forgery by default.
_DEFAULT_INSECURE_KEY = "your-secret-key-change-in-production"
_env_key = os.getenv("AUTH_SECRET_KEY", "")
if _env_key and _env_key != _DEFAULT_INSECURE_KEY:
    SECRET_KEY = _env_key
else:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "AUTH_SECRET_KEY is not set or uses the insecure default. "
        "Generated a random session-scoped key. Set AUTH_SECRET_KEY in production "
        "to persist tokens across restarts."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "quickpulse")


class Token(BaseModel):
    access_token: str
    token_type: str


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc
    return username


@router.post("/token", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    if not hmac.compare_digest(form_data.password.encode(), AUTH_PASSWORD.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/verify")
async def verify_token(username: str = Depends(get_current_user)):
    """Verify that the current token is valid. Returns 401 if expired/invalid."""
    return {"valid": True, "username": username}
