# Session Management with Redis

This application uses Redis as a server-side session store for OAuth2 tokens and user data, providing secure, scalable session management.

## Why Redis?

- **Security**: Tokens never exposed to browser JavaScript
- **Performance**: Sub-millisecond session lookups
- **Scalability**: Shared session store for multiple app instances
- **Expiration**: Built-in TTL for automatic cleanup
- **Atomic Operations**: Thread-safe session updates

## Architecture

### SessionStore Implementation

Location: `src/infrastructure/session_store.py`

The `SessionStore` class provides a clean interface to Redis:

```python
from infrastructure.session_store import SessionStore

# Create session with OAuth2 tokens
session_id = session_store.create_session(
    user_id="user123",
    tokens={
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "id_token": "eyJ..."
    },
    user_data={
        "username": "admin",
        "roles": ["admin", "manager"]
    }
)

# Retrieve session
session = session_store.get_session(session_id)
# Returns: {
#   "user_id": "user123",
#   "tokens": {...},
#   "user_data": {...}
# }

# Delete session (logout)
session_store.delete_session(session_id)
```

## Session Lifecycle

### 1. Login (Session Creation)

During OAuth2 callback, the backend:

1. Exchanges authorization code for tokens
2. Extracts user info from ID token
3. Creates session with tokens and user data
4. Generates secure session ID
5. Sets httpOnly cookie with session ID

```python
@get("/api/auth/callback")
async def callback(code: str, response: Response):
    # Exchange code for tokens
    tokens = await oauth2_client.exchange_code(code)

    # Extract user info
    user_info = decode_id_token(tokens['id_token'])

    # Store in session
    session_id = self.session_store.create_session(
        user_id=user_info['sub'],
        tokens=tokens,
        user_data={
            "username": user_info['preferred_username'],
            "roles": user_info.get('roles', [])
        }
    )

    # Set cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600
    )
```

### 2. Authenticated Requests

On each request:

1. Browser sends session cookie automatically
2. Middleware injects AuthService
3. Dependency extracts session_id from cookie
4. AuthService retrieves session from Redis
5. Request proceeds with user context

### 3. Logout (Session Deletion)

On logout:

1. Backend receives logout request
2. Session deleted from Redis
3. Cookie cleared from browser
4. User redirected to public page

```python
@post("/api/auth/logout")
async def logout(
    response: Response,
    session_id: Optional[str] = Cookie(None)
):
    if session_id:
        self.session_store.delete_session(session_id)

    response.delete_cookie("session_id")
    return {"message": "Logged out"}
```

## Session Data Structure

### Redis Key Format

```
session:<session_id>
```

### Session Data (JSON)

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "id_token": "eyJhbGciOiJSUzI1NiIs...",
    "expires_in": 3600,
    "refresh_expires_in": 1800,
    "token_type": "Bearer"
  },
  "user_data": {
    "username": "admin",
    "email": "admin@example.com",
    "roles": ["admin", "manager"],
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

## Configuration

### Redis Connection

Set via environment variables in `.env`:

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=optional_password
```

### Session TTL

Default: 3600 seconds (1 hour)

Configurable in `application/settings.py`:

```python
SESSION_TTL = 3600  # seconds
```

## Docker Setup

The application includes Redis in `docker-compose.yml`:

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "${REDIS_PORT:-6379}:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes
```

Start with:

```bash
make docker-up
```

## Testing Session Store

Unit tests in `tests/test_session_store.py`:

```python
def test_create_and_get_session():
    session_id = session_store.create_session(
        user_id="test_user",
        tokens={"access_token": "test_token"},
        user_data={"username": "testuser"}
    )

    session = session_store.get_session(session_id)
    assert session["user_id"] == "test_user"
    assert session["tokens"]["access_token"] == "test_token"

def test_session_expiration():
    session_id = session_store.create_session(
        user_id="test_user",
        tokens={},
        user_data={},
        ttl=1  # 1 second
    )

    time.sleep(2)
    session = session_store.get_session(session_id)
    assert session is None
```

## Monitoring

### Redis CLI

Check sessions manually:

```bash
# Connect to Redis
redis-cli

# List all sessions
KEYS session:*

# Get session data
GET session:<session_id>

# Check TTL
TTL session:<session_id>

# Count active sessions
EVAL "return #redis.call('keys', 'session:*')" 0
```

### Observability

The application includes OpenTelemetry tracing:

- Session creation spans
- Session lookup timing
- Redis connection metrics
- Error tracking

## Security Considerations

- ✅ **Session ID Generation** - Cryptographically secure random UUIDs
- ✅ **httpOnly Cookies** - Prevent JavaScript access
- ✅ **Secure Flag** - HTTPS-only in production
- ✅ **SameSite Attribute** - CSRF protection
- ✅ **Token Encryption** - Consider encrypting tokens in Redis
- ✅ **TTL Management** - Automatic cleanup of expired sessions
- ✅ **Connection Security** - Use TLS for Redis in production

## Production Recommendations

1. **Redis Cluster** - Use Redis Cluster or Sentinel for high availability
2. **TLS/SSL** - Encrypt Redis connections
3. **Authentication** - Require Redis password
4. **Backup** - Regular Redis backups (AOF + RDB)
5. **Monitoring** - Track session metrics (creation rate, active count)
6. **Token Encryption** - Encrypt sensitive tokens at rest
7. **Session Limits** - Limit sessions per user

## Troubleshooting

### Session Not Found

**Symptom**: 401 Unauthorized with valid cookie

**Causes**:

- Session expired (TTL reached)
- Redis connection lost
- Session manually deleted

**Solution**: Redirect to login

### Redis Connection Error

**Symptom**: "Error connecting to Redis"

**Checks**:

- Redis service running: `docker compose ps redis`
- Connection settings in `.env`
- Network connectivity
- Redis logs: `docker compose logs redis`

### Session Leaks

**Symptom**: Growing Redis memory usage

**Causes**:

- Sessions not deleted on logout
- TTL not set correctly
- Abandoned sessions

**Solution**:

- Verify TTL configuration
- Implement session cleanup job
- Monitor active session count

## Related Documentation

- [Authentication Flows](./authentication-flows.md) - Dual authentication system
- [Authorization](./authorization.md) - OAuth2/OIDC and RBAC
- [Security Guide](./security.md) - Security best practices
- [Docker Environment](../deployment/docker-environment.md) - Redis setup
