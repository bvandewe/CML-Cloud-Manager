# Authentication

This starter app implements a comprehensive dual authentication system supporting both browser-based session cookies and JWT Bearer tokens, enabling secure access for both UI and programmatic API clients.

## Authentication Methods

### 1. Session Cookie Authentication (Primary for UI)

Browser-based authentication using httpOnly cookies for security.

**Flow:**

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Backend
    participant Keycloak
    participant Redis

    User->>Browser: Click "Login"
    Browser->>Backend: GET /auth/login
    Backend->>Browser: Redirect to Keycloak
    Browser->>Keycloak: OAuth2 Authorization Request

    Keycloak->>User: Show Login Page
    User->>Keycloak: Enter Credentials
    Keycloak->>Keycloak: Validate Credentials

    Keycloak->>Browser: Redirect with Auth Code
    Browser->>Backend: GET /auth/callback?code=xyz

    Backend->>Keycloak: Exchange Code for Tokens
    Keycloak->>Backend: Access Token + Refresh Token + ID Token

    Backend->>Redis: Store Tokens (session_id: tokens)
    Redis->>Backend: OK

    Backend->>Browser: Set httpOnly Cookie (session_id)
    Browser->>User: Logged In

    Note over Browser,Backend: Subsequent Requests
    Browser->>Backend: API Request + Cookie
    Backend->>Redis: Get Session by ID
    Redis->>Backend: Return Tokens
    Backend->>Backend: Validate & Extract User
    Backend->>Browser: Authorized Response
```

**Security Features:**

- httpOnly cookies prevent XSS attacks
- SameSite attribute prevents CSRF
- Secure flag enforces HTTPS
- Tokens never exposed to JavaScript

For more details on how the session store is implemented, see [Session Management](session-management.md).

### 2. JWT Bearer Token Authentication (For API Clients)

Token-based authentication for programmatic access, testing, and API clients.

**Flow:**

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API
    participant Keycloak
    participant Backend

    Note over Client,Keycloak: Token Acquisition
    Client->>Keycloak: POST /token (client_credentials or password grant)
    activate Keycloak
    Keycloak->>Keycloak: Validate Credentials
    Keycloak->>Client: Return JWT Access Token
    deactivate Keycloak

    Note over Client,Backend: API Request with Token
    Client->>Backend: API Request<br/>Authorization: Bearer <token>
    activate Backend
    Backend->>Backend: Extract JWT from Header
    Backend->>Backend: Validate Token Signature
    Backend->>Backend: Verify Token Claims<br/>(expiry, issuer, audience)
    Backend->>Backend: Extract User Context<br/>(username, roles)

    alt Token Valid
        Backend->>Backend: Process Request
        Backend->>Client: Authorized Response
    else Token Invalid/Expired
        Backend->>Client: 401 Unauthorized
    end
    deactivate Backend

    Note over Client: Token Refresh (when expired)
    Client->>Keycloak: POST /token (refresh_token grant)
    Keycloak->>Client: New Access Token
```

## Token Details

### RS256 vs HS256

- Keycloak issues **RS256** signed tokens (asymmetric). We verify using the public key from the JWKS endpoint.
- A deprecated **HS256** path remains for legacy tokens created internally; this is only used if the token header explicitly declares the HS256 algorithm.

### JWKS Handling

- The JWKS endpoint is fetched from `<KEYCLOAK_URL>/realms/<realm>/protocol/openid-connect/certs`.
- The keys are cached in-memory for 1 hour to reduce latency.
- The cache is pre-warmed on application startup.

### Token Claim Validation

The application can be configured to validate the following token claims:

- `iss` (issuer): `VERIFY_ISSUER` / `EXPECTED_ISSUER`
- `aud` (audience): `VERIFY_AUDIENCE` / `EXPECTED_AUDIENCE`

### Role Mapping

Roles are extracted from the `realm_access.roles` claim in the JWT.

## FastAPI Integration

- The `get_current_user` dependency handles both session cookies and bearer tokens.
- Role-based access control is provided by the `require_roles` dependency.
- The `/api/auth/refresh` endpoint allows for token rotation.
- Expired bearer tokens will result in a `401 Unauthorized` response.

## OpenAPI Configuration

The OpenAPI documentation (Swagger UI) is configured with two security schemes to support both authentication methods:

- `OAuth2AuthorizationCode`
- `HTTPBearer`
