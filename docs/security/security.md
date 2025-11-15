# Security Best Practices & Hardening

This guide consolidates the security features implemented in the template and outlines recommended hardening steps for production deployments.

## ☂️ Threat Model Overview

Primary concerns:

- Token theft (XSS / storage leakage)
- CSRF attacks against authenticated endpoints
- Replay or forged JWTs
- Privilege escalation via malformed claims
- Secret/config leakage in source control
- Unauthorized long-lived sessions



## ✅ Implemented Protections

| Category | Protection | Notes |
|----------|-----------|-------|
| Token Storage | httpOnly session cookie | Not readable via JS; server-side session indirection |
| CSRF | SameSite cookie (Lax/Strict recommended) | Prevents cross-site form auto-submission |
| Transport | HTTPS (enforced via Secure flag) | Mandatory in production deployment |
| JWT Signing | RS256 via JWKS | Asymmetric verification, no shared secret leakage |
| Claim Validation | Issuer + Audience checks | Configurable via settings variables |
| Expiry Handling | RFC6750 `WWW-Authenticate` header | Clear client feedback on expired tokens |
| Session Rotation | Refresh endpoint + auto-refresh leeway | Reduces window for stolen token usage |
| Redis Session TTL | Expiration enforced in backend | Mitigates indefinite session reuse |
| Security Headers | Can be added at ASGI middleware layer | See Hardening section |
| Dependency Audit | `bandit` & `detect-secrets` pre-commit hooks | CI gating recommended |
| Role Enforcement | Application-layer RBAC | Defense in depth beyond controller layer |

## 🔐 Configuration Checklist

Environment variables to review:

```bash
# OIDC
KEYCLOAK_SERVER_URL=https://keycloak.example.com
KEYCLOAK_REALM=prod-realm
KEYCLOAK_CLIENT_ID=portal-web-app

# Redis (if enabled)
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
REDIS_KEY_PREFIX=session:

# Token refresh leeway (seconds before expiry to auto-refresh)
REFRESH_AUTO_LEEWAY_SECONDS=120

# Issuer/Audience validation
VERIFY_ISSUER=true
EXPECTED_ISSUER=https://keycloak.example.com/realms/prod-realm
VERIFY_AUDIENCE=true
EXPECTED_AUDIENCE=portal-web-app
```

## 🛡️ Hardening Recommendations

### 1. Enforce Secure Cookie Settings

Set cookie attributes:

- `Secure=True` (production only)
- `HttpOnly=True`
- `SameSite=Lax` or `Strict`
- Short session TTL + refresh capability



### 2. Add Security Middleware

Use a custom ASGI middleware or FastAPI dependency to add headers:

```python
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",  # modern browsers ignore/obsolete
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
}

def add_security_headers(app):
    async def middleware(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                for k, v in SECURITY_HEADERS.items():
                    headers.append((k.lower().encode(), v.encode()))
            await send(message)
        await app(scope, receive, send_wrapper)
    return middleware
```

### 3. Restrict CORS

Only allow trusted origins; avoid wildcard `*` if credentials/cookies involved.



### 4. Secrets Management

Use platform secret stores (Vault, AWS Secrets Manager). Avoid committing secrets; rely on `detect-secrets` baseline scanning.



### 5. Audit & Monitoring

- Centralize logs (e.g., OpenTelemetry collector already present)
- Track auth events: login, refresh, failed auth, role violations
- Alert on anomaly (excessive refresh attempts, high invalid token rate)



### 6. Rate Limiting

Protect login and token refresh endpoints to mitigate brute force. (Implement via reverse proxy or ASGI middleware.)



### 7. Dependency Hygiene

- Pin versions in `pyproject.toml`
- Run `poetry update --dry-run` periodically to review security patches
- Integrate vulnerability scanning (GitHub Dependabot / OSS Index)



### 8. TLS Enforcement

Terminate TLS at load balancer or ingress; never serve plaintext externally.



### 9. Minimal Claims

Avoid unnecessary PII or extraneous claims in tokens; store sensitive fields server-side in session rather than embedding into JWT.



### 10. Least Privilege Roles

Keep role surface minimal. Consider permission flags internally rather than proliferating roles.



## 🚫 Common Pitfalls

- Storing tokens in `localStorage` (vulnerable to XSS) – this template avoids it.
- Omitting audience validation – opens door to token substitution across clients.
- Overly long token lifetimes – increases exposure window.
- Wildcard CORS + credentials – allows CSRF-like abuse.



## 🧪 Testing Security

Add targeted tests:

- Expired token → 401 with `WWW-Authenticate: error="invalid_token"`.
- Wrong issuer/audience → 401 with precise error reason.
- Session cookie absent + no Bearer header → 401 unauthorized.
- Refresh near expiry rotates token (simulate time shift).



## 🔄 Refresh Strategy Notes

Auto-refresh occurs within configured leeway to reduce race conditions for expiring tokens. Ensure refresh endpoint is guarded and logs events.



## 📌 Roadmap (Future Hardening)

- Add MFA support (Keycloak TOTP integration)
- Add signed/encrypted cookies (if storing transient data client-side)
- Introduce authorization policies beyond simple role checks
- Integrate rate limiting middleware & login attempt counters
- Provide security events dashboard



## 📚 References

- OAuth 2.0 RFC 6749
- OIDC Core Spec
- RFC 7519 (JWT)
- OWASP Cheat Sheets (Authentication, Session Management, XSS Prevention)

---
Last updated: 2025-11-07
