from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from services.database import get_db_connection
from datetime import datetime, timedelta
import secrets
import hashlib

router = APIRouter(prefix="/api", tags=["Authentication"])

# Simple token storage (in production, use Redis or database)
# Token format: {token: {user_info, expires_at}}
token_store = {}

# Token expiration time (24 hours)
TOKEN_EXPIRATION_HOURS = 24


# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    status: str
    token: Optional[str] = None
    user: Optional[dict] = None
    expires_at: Optional[str] = None
    message: Optional[str] = None


class TokenResponse(BaseModel):
    status: str
    valid: bool
    user: Optional[dict] = None
    message: Optional[str] = None


def get_permissions(role_name: str) -> list:
    """Get permissions for a role"""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT permission_name FROM role_permissions WHERE role_name = ?",
        (role_name,)
    ).fetchall()
    conn.close()
    return [row["permission_name"] for row in rows]


def generate_token() -> str:
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)


def cleanup_expired_tokens():
    """Remove expired tokens from store"""
    current_time = datetime.now()
    expired_tokens = [
        token for token, data in token_store.items()
        if data.get("expires_at", current_time) < current_time
    ]
    for token in expired_tokens:
        del token_store[token]


@router.post("/auth/login", response_model=LoginResponse)
async def api_login(credentials: LoginRequest):
    """
    Authenticate user and return API token
    
    Returns a token that can be used for subsequent API requests.
    Token expires after 24 hours.
    """
    username = credentials.username
    password = credentials.password
    print(username)
    
    # Cleanup expired tokens first
    cleanup_expired_tokens()
    
    conn = get_db_connection()
    
    # Check for admin user
    if username == "admin" and password == "123456":
        user_info = {
            "username": "admin",
            "role": "administrator",
            "permissions": [
                'Archive', 'Dashboard', 'Data analysis', 
                'Remote Maintain', 'System Management', 
                'System Task', 'Warehouse'
            ]
        }
    else:
        # Check database
        user = conn.execute(
            "SELECT * FROM users WHERE user_name = ? AND password = ?",
            (username, password)
        ).fetchone()
        conn.close()
        
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )
        
        # Check if user is active (status must be "Идэвхитэй")
        if user["status"] != "Идэвхитэй":
            raise HTTPException(
                status_code=403,
                detail="User account is inactive"
            )
        
        permissions = get_permissions(user["role_name"])
        user_info = {
            "username": user["user_name"],
            "role": user["role_name"],
            "nick_name": user.get("nick_name"),
            "email": user.get("email"),
            "phone_number": user.get("phone_number"),
            "permissions": permissions
        }
    
    # Generate token
    token = generate_token()
    expires_at = datetime.now() + timedelta(hours=TOKEN_EXPIRATION_HOURS)
    
    # Store token
    token_store[token] = {
        "user_info": user_info,
        "expires_at": expires_at,
        "created_at": datetime.now()
    }
    
    return {
        "status": "success",
        "token": token,
        "user": user_info,
        "expires_at": expires_at.isoformat(),
        "message": "Login successful"
    }


@router.post("/auth/validate")
async def validate_token(token: str = Header(None, alias="X-API-Token")):
    """
    Validate an API token
    
    Returns user information if token is valid.
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token is required"
        )
    
    cleanup_expired_tokens()
    
    token_data = token_store.get(token)
    
    if not token_data:
        return {
            "status": "error",
            "valid": False,
            "message": "Invalid or expired token"
        }
    
    # Check if expired
    if token_data["expires_at"] < datetime.now():
        del token_store[token]
        return {
            "status": "error",
            "valid": False,
            "message": "Token has expired"
        }
    
    return {
        "status": "success",
        "valid": True,
        "user": token_data["user_info"],
        "message": "Token is valid"
    }


@router.post("/auth/logout")
async def api_logout(token: str = Header(None, alias="X-API-Token")):
    """
    Logout and invalidate token
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token is required"
        )
    
    if token in token_store:
        del token_store[token]
        return {
            "status": "success",
            "message": "Logged out successfully"
        }
    else:
        return {
            "status": "success",
            "message": "Token was already invalid"
        }


@router.get("/auth/me")
async def get_current_user(token: str = Header(None, alias="X-API-Token")):
    """
    Get current authenticated user information
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token is required"
        )
    
    cleanup_expired_tokens()
    
    token_data = token_store.get(token)
    
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Check if expired
    if token_data["expires_at"] < datetime.now():
        del token_store[token]
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    
    return {
        "status": "success",
        "user": token_data["user_info"]
    }


@router.get("/auth/tokens")
async def list_active_tokens(token: str = Header(None, alias="X-API-Token")):
    """
    List all active tokens (admin only)
    """
    if not token:
        raise HTTPException(status_code=401, detail="Token is required")
    
    cleanup_expired_tokens()
    
    token_data = token_store.get(token)
    if not token_data or token_data["user_info"].get("role") != "administrator":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    active_tokens = []
    for t, data in token_store.items():
        active_tokens.append({
            "token_preview": f"{t[:8]}...{t[-4:]}" if len(t) > 12 else "***",
            "username": data["user_info"].get("username"),
            "role": data["user_info"].get("role"),
            "created_at": data["created_at"].isoformat(),
            "expires_at": data["expires_at"].isoformat()
        })
    
    return {
        "status": "success",
        "count": len(active_tokens),
        "data": active_tokens
    }


# Dependency function for protecting API endpoints
async def verify_token(token: str = Header(None, alias="X-API-Token")):
    """
    Dependency function to verify API token.
    Use this in API endpoints that require authentication.
    
    Example:
        @router.get("/protected-endpoint")
        async def protected_endpoint(user: dict = Depends(verify_token)):
            return {"message": f"Hello {user['username']}"}
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide X-API-Token header."
        )
    
    cleanup_expired_tokens()
    
    token_data = token_store.get(token)
    
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Check if expired
    if token_data["expires_at"] < datetime.now():
        del token_store[token]
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please login again."
        )
    
    return token_data["user_info"]

