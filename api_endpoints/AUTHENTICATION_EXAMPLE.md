# Authentication API Usage Examples

This document provides examples of how to use the authentication API with different programming languages and tools.

## Using curl

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "123456"
  }'
```

### Using token in subsequent requests
```bash
# Store token in variable (bash/zsh)
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}' \
  | jq -r '.token')

# Use token
curl http://localhost:8000/api/meters/installed \
  -H "X-API-Token: $TOKEN"
```

## Python Example

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000/api"

# Login
login_response = requests.post(
    f"{BASE_URL}/auth/login",
    json={
        "username": "admin",
        "password": "123456"
    }
)

if login_response.status_code == 200:
    data = login_response.json()
    token = data["token"]
    print(f"Logged in as {data['user']['username']}")
    print(f"Token expires at: {data['expires_at']}")
else:
    print("Login failed:", login_response.json())
    exit(1)

# Use token in subsequent requests
headers = {
    "X-API-Token": token,
    "Content-Type": "application/json"
}

# Get installed meters
meters_response = requests.get(
    f"{BASE_URL}/meters/installed",
    headers=headers
)

if meters_response.status_code == 200:
    meters = meters_response.json()
    print(f"Found {meters['total']} meters")
    for meter in meters["data"]:
        print(f"  - {meter['meter_number']}: {meter['status']}")
else:
    print("Error:", meters_response.json())

# Get current user info
user_response = requests.get(
    f"{BASE_URL}/auth/me",
    headers=headers
)

if user_response.status_code == 200:
    user = user_response.json()
    print(f"\nCurrent user: {user['user']['username']}")
    print(f"Role: {user['user']['role']}")
    print(f"Permissions: {', '.join(user['user']['permissions'])}")

# Logout
logout_response = requests.post(
    f"{BASE_URL}/auth/logout",
    headers=headers
)
print("\nLogged out:", logout_response.json())
```

## JavaScript/Node.js Example

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000/api';

async function example() {
    try {
        // Login
        const loginResponse = await axios.post(`${BASE_URL}/auth/login`, {
            username: 'admin',
            password: '123456'
        });
        
        const { token, user, expires_at } = loginResponse.data;
        console.log(`Logged in as ${user.username}`);
        console.log(`Token expires at: ${expires_at}`);
        
        // Create axios instance with default headers
        const api = axios.create({
            baseURL: BASE_URL,
            headers: {
                'X-API-Token': token,
                'Content-Type': 'application/json'
            }
        });
        
        // Get installed meters
        const metersResponse = await api.get('/meters/installed');
        console.log(`Found ${metersResponse.data.total} meters`);
        
        // Get readings
        const readingsResponse = await api.get('/readings/energy-profile/18130957', {
            params: {
                start_date: '2024-01-01 00:00:00',
                end_date: '2024-01-31 23:59:59',
                limit: 10
            }
        });
        console.log(`Found ${readingsResponse.data.total} readings`);
        
        // Get current user
        const userResponse = await api.get('/auth/me');
        console.log('Current user:', userResponse.data.user);
        
        // Logout
        await api.post('/auth/logout');
        console.log('Logged out successfully');
        
    } catch (error) {
        console.error('Error:', error.response?.data || error.message);
    }
}

example();
```

## Python with Session Management

```python
import requests
from datetime import datetime, timedelta

class MeterAPI:
    def __init__(self, base_url="http://localhost:8000/api"):
        self.base_url = base_url
        self.session = requests.Session()
        self.token = None
        self.token_expires = None
    
    def login(self, username, password):
        """Login and store token"""
        response = self.session.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        
        data = response.json()
        self.token = data["token"]
        self.token_expires = datetime.fromisoformat(data["expires_at"])
        self.session.headers.update({"X-API-Token": self.token})
        
        return data
    
    def is_token_valid(self):
        """Check if token is still valid"""
        if not self.token or not self.token_expires:
            return False
        return datetime.now() < self.token_expires
    
    def ensure_authenticated(self):
        """Ensure we have a valid token"""
        if not self.is_token_valid():
            raise Exception("Token expired. Please login again.")
    
    def get_meters(self, **params):
        """Get installed meters"""
        self.ensure_authenticated()
        response = self.session.get(
            f"{self.base_url}/meters/installed",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_readings(self, meter_number, reading_type="energy-profile", **params):
        """Get readings for a meter"""
        self.ensure_authenticated()
        response = self.session.get(
            f"{self.base_url}/readings/{reading_type}/{meter_number}",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def logout(self):
        """Logout and clear token"""
        if self.token:
            self.session.post(f"{self.base_url}/auth/logout")
        self.token = None
        self.token_expires = None
        self.session.headers.pop("X-API-Token", None)

# Usage
api = MeterAPI()
api.login("admin", "123456")

meters = api.get_meters(limit=10)
print(f"Found {meters['total']} meters")

readings = api.get_readings(
    "18130957",
    start_date="2024-01-01 00:00:00",
    end_date="2024-01-31 23:59:59"
)
print(f"Found {readings['total']} readings")

api.logout()
```

## PowerShell Example

```powershell
$baseUrl = "http://localhost:8000/api"

# Login
$loginBody = @{
    username = "admin"
    password = "123456"
} | ConvertTo-Json

$loginResponse = Invoke-RestMethod -Uri "$baseUrl/auth/login" `
    -Method Post `
    -Body $loginBody `
    -ContentType "application/json"

$token = $loginResponse.token
Write-Host "Logged in as $($loginResponse.user.username)"
Write-Host "Token: $token"

# Create headers with token
$headers = @{
    "X-API-Token" = $token
    "Content-Type" = "application/json"
}

# Get meters
$metersResponse = Invoke-RestMethod -Uri "$baseUrl/meters/installed" `
    -Method Get `
    -Headers $headers

Write-Host "Found $($metersResponse.total) meters"

# Logout
Invoke-RestMethod -Uri "$baseUrl/auth/logout" `
    -Method Post `
    -Headers $headers
Write-Host "Logged out"
```

## Error Handling

All authentication errors return appropriate HTTP status codes:

- **401 Unauthorized**: Invalid credentials, missing token, or expired token
- **403 Forbidden**: User account is inactive or insufficient permissions
- **400 Bad Request**: Invalid request format

Example error response:
```json
{
  "detail": "Invalid username or password"
}
```

Example error handling in Python:
```python
try:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "wrong"}
    )
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        print("Authentication failed: Invalid credentials")
    elif e.response.status_code == 403:
        print("Access denied: Account inactive")
    else:
        print(f"Error: {e.response.json()}")
```

