# Add Cisco IDP

```json
...
    "identityProviders": [
        {
            "alias": "corporate-sso",
            "displayName": "Corporate SSO",
            "providerId": "oidc",
            "enabled": true,
            "updateProfileFirstLoginMode": "on",
            "trustEmail": true,
            "storeToken": false,
            "addReadTokenRoleOnCreate": false,
            "authenticateByDefault": false,
            "linkOnly": false,
            "firstBrokerLoginFlowAlias": "first broker login",
            "config": {
                "hideOnLoginPage": "false",
                "userInfoUrl": "https://your-idp.com/.well-known/openid-configuration/userinfo",
                "validateSignature": "true",
                "clientId": "your-client-id",
                "tokenUrl": "https://your-idp.com/oauth2/token",
                "jwksUrl": "https://your-idp.com/.well-known/jwks.json",
                "issuer": "https://your-idp.com",
                "useJwksUrl": "true",
                "authorizationUrl": "https://your-idp.com/oauth2/authorize",
                "clientSecret": "your-client-secret",  # pragma: allowlist secret
                "clientAuthMethod": "client_secret_post",
                "syncMode": "IMPORT",
                "defaultScope": "openid profile email"
            }
        }
    ],
    "identityProviderMappers": [
        {
            "name": "email-to-username",
            "identityProviderAlias": "corporate-sso",
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "syncMode": "IMPORT",
                "claim": "email",
                "user.attribute": "username"
            }
        },
        {
            "name": "email",
            "identityProviderAlias": "corporate-sso",
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "syncMode": "IMPORT",
                "claim": "email",
                "user.attribute": "email"
            }
        },
        {
            "name": "firstName",
            "identityProviderAlias": "corporate-sso",
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "syncMode": "IMPORT",
                "claim": "given_name",
                "user.attribute": "firstName"
            }
        },
        {
            "name": "lastName",
            "identityProviderAlias": "corporate-sso",
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "syncMode": "IMPORT",
                "claim": "family_name",
                "user.attribute": "lastName"
            }
        },
        {
            "name": "groups-mapper",
            "identityProviderAlias": "corporate-sso",
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "syncMode": "IMPORT",
                "claim": "groups",
                "user.attribute": "groups"
            }
        }
    ],
```
