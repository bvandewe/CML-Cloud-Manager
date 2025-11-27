# Event Player Proxy Integration Guide

## Problem Analysis

The `event-player` service is currently failing to authenticate users in the production environment when hosted under the `/events/` subpath.

**Symptoms:**

1. User initiates login from `event-player`.
2. Keycloak redirects user to the Main App (root path `/`) instead of `event-player`.
3. `event-player` frontend reports `{"authenticated": false}`.

**Root Cause:**
The `event-player` backend is likely generating the OIDC `redirect_uri` based on the request's host header but ignoring the path prefix (`/events`) introduced by the Nginx reverse proxy.

- **Current Behavior**: Generates `https://admin.ciscolablets.com/login/callback`
- **Required Behavior**: Generates `https://admin.ciscolablets.com/events/login/callback`

Because the generated URI is missing `/events`, Keycloak redirects the browser to the Main App (handled by `location /` in Nginx), so `event-player` never receives the authorization code.

## Required Code Changes

To support subpath hosting while maintaining compatibility with standalone deployments (dev environment), the application must become "Proxy Aware".

### 1. Middleware for Proxy Headers

Implement middleware to inspect standard proxy headers and adjust the application's base URL context.

**Headers to respect:**

- `X-Forwarded-Prefix`: The path prefix added by the reverse proxy (e.g., `/events`).
- `X-Forwarded-Proto`: The protocol (http/https).
- `X-Forwarded-Host`: The original host.

**Implementation Logic (Pseudo-code):**

```python
def proxy_middleware(request, call_next):
    # 1. Detect Prefix
    prefix = request.headers.get("X-Forwarded-Prefix", "")

    # 2. Store in request context
    request.state.base_path = prefix

    # 3. (Optional) Strip prefix from path if the router expects raw paths
    # Many frameworks (like FastAPI/Starlette) handle this automatically
    # if you set the 'root_path' on the application.

    response = await call_next(request)
    return response
```

### 2. OIDC Redirect URI Generation

When constructing the `redirect_uri` for the OAuth2 authorization request, append the detected prefix.

**Current Logic (Likely):**

```python
redirect_uri = f"{request.scheme}://{request.host}/login/callback"
```

**New Logic:**

```python
# Get prefix from header or config (default to empty string)
prefix = request.headers.get("X-Forwarded-Prefix", "")

# Ensure prefix starts with / if present, and doesn't end with /
if prefix:
    prefix = "/" + prefix.strip("/")

redirect_uri = f"{request.scheme}://{request.host}{prefix}/login/callback"
```

### 3. Frontend Base Path Configuration

The frontend needs to know it is running under a subpath to correctly fetch assets and make API calls, without relying solely on Nginx `sub_filter` rewriting (which is brittle).

**Recommendation:**
Inject the configuration via the `index.html` or a configuration endpoint.

**Option A: HTML Base Tag (Simplest)**
The backend should render the `index.html` dynamically or Nginx can inject it (we are already doing this via `sub_filter`, but code support is better).

```html
<base href="/events/">
```

**Option B: Runtime Configuration**
The frontend should fetch `GET /auth/status` (or similar) which returns the context.

```json
{
  "authenticated": false,
  "base_path": "/events"  // <--- Add this
}
```

Frontend router setup:

```javascript
const basePath = apiResponse.base_path || "/";
const router = createRouter({
  history: createWebHistory(basePath),
  routes: [...]
});
```

## Compatibility Check

| Environment | Proxy | Header `X-Forwarded-Prefix` | Resulting URI | Status |
|-------------|-------|-----------------------------|---------------|--------|
| **Dev** | None | (Missing) | `http://localhost:8080/login/callback` | ✅ Works (Standalone) |
| **Prod** | Nginx | `/events` | `https://admin.ciscolablets.com/events/login/callback` | ✅ Works (Subpath) |

## Checklist for Implementation

1. [ ] **Backend**: Add logic to read `X-Forwarded-Prefix`.
2. [ ] **Backend**: Update `OAuth2` client initialization to use the prefixed `redirect_uri`.
3. [ ] **Backend**: Ensure `Cookie` path is set to the prefix (or `/` if acceptable).
4. [ ] **Frontend**: Update API client to prepend base path to requests (if not using relative paths).
