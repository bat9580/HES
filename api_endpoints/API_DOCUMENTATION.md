# Smart Meter Monitoring System - REST API Documentation

This document describes the REST API endpoints available for integrating with the Smart Meter Monitoring System.

## Base URL
All API endpoints are prefixed with `/api`

## Authentication

The API uses token-based authentication. To access protected endpoints:

1. **Login** to get a token via `POST /api/auth/login`
2. **Include the token** in subsequent requests using the `X-API-Token` header
3. **Tokens expire** after 24 hours

### Example Authentication Flow

```bash
# 1. Login to get token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "123456"
  }'

# Response:
{
  "status": "success",
  "token": "abc123xyz...",
  "user": {...},
  "expires_at": "2024-01-02T12:00:00"
}

# 2. Use token in subsequent requests
curl http://localhost:8000/api/meters/installed \
  -H "X-API-Token: abc123xyz..."
```

---

## Authentication API (`/api/auth`)

### Login
- **POST** `/api/auth/login`
- Body: JSON with `username` and `password`
- Response: JSON with token, user info, and expiration time
- Example:
```json
{
  "username": "admin",
  "password": "123456"
}
```

### Validate Token
- **POST** `/api/auth/validate`
- Header: `X-API-Token`
- Response: JSON indicating if token is valid and user info

### Get Current User
- **GET** `/api/auth/me`
- Header: `X-API-Token`
- Response: JSON with current user information

### Logout
- **POST** `/api/auth/logout`
- Header: `X-API-Token`
- Response: JSON confirming logout (invalidates token)

### List Active Tokens (Admin Only)
- **GET** `/api/auth/tokens`
- Header: `X-API-Token` (must be admin token)
- Response: JSON with list of all active tokens

---

## Endpoints Overview

### Meters API (`/api/meters`)

#### Get Installed Meters
- **GET** `/api/meters/installed`
- Query Parameters:
  - `meter_number` (optional): Filter by meter number (partial match)
  - `line` (optional): Filter by line
  - `status` (optional): Filter by status
  - `limit` (optional, default: 100): Max results per page
  - `offset` (optional, default: 0): Pagination offset
- Response: JSON with list of installed meters

#### Get Single Installed Meter
- **GET** `/api/meters/installed/{meter_number}`
- Response: JSON with meter details

#### Create Installed Meter
- **POST** `/api/meters/installed`
- Body: JSON with meter details (meter_number, com_address, password, device_type, type, etc.)
- Response: JSON with success message

#### Update Installed Meter
- **PUT** `/api/meters/installed/{meter_number}`
- Body: JSON with fields to update
- Response: JSON with success message

#### Delete Installed Meter
- **DELETE** `/api/meters/installed/{meter_number}`
- Response: JSON with success message

#### Get Registered Meters
- **GET** `/api/meters/registered`
- Query Parameters: `meter_number`, `status`, `limit`, `offset`
- Response: JSON with list of registered meters

#### Get Meter Connection Status
- **GET** `/api/meters/{meter_number}/status`
- Response: JSON with connection status and meter info

#### Get Connected Meters
- **GET** `/api/meters/connected`
- Response: JSON with list of currently connected meters

---

### Readings API (`/api/readings`)

#### Get Energy Profile Readings
- **GET** `/api/readings/energy-profile`
- Query Parameters:
  - `meter_number` (optional): Filter by meter number
  - `line` (optional): Filter by line
  - `start_date` (optional): Start date (YYYY-MM-DD HH:MM:SS)
  - `end_date` (optional): End date (YYYY-MM-DD HH:MM:SS)
  - `calculated` (optional, default: false): Use calculated values
  - `limit`, `offset`: Pagination
- Response: JSON with energy profile readings

#### Get Energy Profile by Meter
- **GET** `/api/readings/energy-profile/{meter_number}`
- Query Parameters: `start_date`, `end_date`, `calculated`, `limit`, `offset`
- Response: JSON with energy profile readings for specific meter

#### Get Instantaneous Profile Readings
- **GET** `/api/readings/instantaneous`
- Query Parameters: Same as energy profile
- Response: JSON with instantaneous profile readings

#### Get Instantaneous Profile by Meter
- **GET** `/api/readings/instantaneous/{meter_number}`
- Query Parameters: Same as energy profile
- Response: JSON with instantaneous readings for specific meter

#### Get Regular Task Readings
- **GET** `/api/readings/regular`
- Query Parameters: `meter_number`, `line`, `start_date`, `end_date`, `limit`, `offset`
- Response: JSON with regular task readings

#### Get Regular Task Readings by Meter
- **GET** `/api/readings/regular/{meter_number}`
- Query Parameters: `start_date`, `end_date`, `limit`, `offset`
- Response: JSON with regular readings for specific meter

#### Get Latest Reading
- **GET** `/api/readings/{meter_number}/latest`
- Response: JSON with the most recent reading from any table

#### Get Meter Statistics
- **GET** `/api/readings/{meter_number}/statistics`
- Query Parameters: `start_date`, `end_date`, `calculated`
- Response: JSON with statistical summary for the meter

---

### DCU API (`/api/dcus`)

#### Get Registered DCUs
- **GET** `/api/dcus/registered`
- Query Parameters: `dcu_number`, `status`, `limit`, `offset`
- Response: JSON with list of registered DCUs

#### Get Single Registered DCU
- **GET** `/api/dcus/registered/{dcu_number}`
- Response: JSON with DCU details

#### Create Registered DCU
- **POST** `/api/dcus/registered`
- Body: JSON with DCU details (dcu_number, com_address, password, etc.)
- Response: JSON with success message

#### Update Registered DCU
- **PUT** `/api/dcus/registered/{dcu_number}`
- Body: JSON with fields to update
- Response: JSON with success message

#### Delete Registered DCU
- **DELETE** `/api/dcus/registered/{dcu_number}`
- Response: JSON with success message

#### Get Unregistered DCUs
- **GET** `/api/dcus/unregistered`
- Query Parameters: `dcu_number`, `limit`, `offset`
- Response: JSON with list of unregistered DCUs

#### Get DCU Meters
- **GET** `/api/dcus/{dcu_number}/meters`
- Response: JSON with all meters associated with a DCU

---

### System API (`/api/system`)

#### Get System Status
- **GET** `/api/system/status`
- Response: JSON with overall system status, counts, and scheduler info

#### Get System Health
- **GET** `/api/system/health`
- Response: JSON with health check results for database and scheduler

#### Get All Connections
- **GET** `/api/system/connections`
- Response: JSON with all active meter connections

#### Get System Statistics
- **GET** `/api/system/statistics`
- Response: JSON with detailed statistics (meters by status, readings, lines, etc.)

#### Get Scheduled Tasks
- **GET** `/api/system/tasks`
- Response: JSON with database tasks and active scheduler jobs

---

## Response Format

All endpoints return JSON responses in the following format:

```json
{
  "status": "success",
  "data": {...},
  "total": 100,  // For paginated endpoints
  "limit": 100,
  "offset": 0
}
```

Error responses:
```json
{
  "detail": "Error message here"
}
```

## Example Requests

### Login and Get Token
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "123456"
  }'
```

### Get all installed meters (with authentication)
```bash
curl http://localhost:8000/api/meters/installed \
  -H "X-API-Token: YOUR_TOKEN_HERE"
```

### Get readings for a specific meter
```bash
curl "http://localhost:8000/api/readings/energy-profile/18130957?start_date=2024-01-01%2000:00:00&end_date=2024-01-31%2023:59:59" \
  -H "X-API-Token: YOUR_TOKEN_HERE"
```

### Create a new installed meter
```bash
curl -X POST http://localhost:8000/api/meters/installed \
  -H "Content-Type: application/json" \
  -H "X-API-Token: YOUR_TOKEN_HERE" \
  -d '{
    "meter_number": "12345678",
    "com_address": "00000001",
    "password": "password123",
    "device_type": "GPRS Meter",
    "type": "DDSY283SR",
    "CT_ratio": 100,
    "VT_ratio": 1
  }'
```

### Get system health
```bash
curl http://localhost:8000/api/system/health \
  -H "X-API-Token: YOUR_TOKEN_HERE"
```

### Get current user info
```bash
curl http://localhost:8000/api/auth/me \
  -H "X-API-Token: YOUR_TOKEN_HERE"
```

## Protecting Endpoints with Authentication

To make an API endpoint require authentication, use the `verify_token` dependency:

```python
from api_endpoints.auth_api import verify_token
from fastapi import Depends

@router.get("/api/protected-endpoint")
async def protected_endpoint(user: dict = Depends(verify_token)):
    return {
        "message": f"Hello {user['username']}",
        "permissions": user.get("permissions", [])
    }
```

## Notes

- **Authentication**: Most endpoints can be made protected using the `verify_token` dependency
- **Token Expiration**: Tokens expire after 24 hours. Use `/api/auth/login` to get a new token
- **Token Storage**: Tokens are stored in memory. In production, consider using Redis or database storage
- All timestamps are in ISO format or `YYYY-MM-DD HH:MM:SS` format
- Pagination is available on list endpoints with `limit` and `offset` parameters
- Date filters support both start and end dates for range queries
- The `calculated` parameter on reading endpoints returns transformer-corrected values when set to `true`
- **User Status**: Users must have status "Идэвхитэй" (Active) to login

