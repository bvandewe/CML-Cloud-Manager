# Keycloak Identity Provider

Keycloak provides Identity and Access Management (IAM) for the CML Cloud Manager. It handles user authentication, role management, and single sign-on (SSO) for Grafana.

## Configuration

- **Realm**: `cml-cloud-manager`
- **Clients**:
    - `cml-cloud-manager-public`: Public client for the main UI (SPA).
    - `grafana`: Confidential client for Grafana SSO.
    - `cml-cloud-manager-api`: Bearer-only client for API protection.

## Realm Export

The realm configuration is stored in `deployment/keycloak/cml-cloud-manager-realm-export.json`. This file is automatically imported on startup.

### Updating the Realm

1. Make changes in the Keycloak Admin Console (`/auth/`).
2. Export the realm configuration.
3. Save the export to `deployment/keycloak/cml-cloud-manager-realm-export.json`.
4. Commit the changes to git.

## Admin Access

- **URL**: `http://<host>/auth/`
- **Default Credentials**: `admin` / `admin` (Change immediately in production!)

## Integration with Grafana

Keycloak is configured as an OAuth2 provider for Grafana. Users with the `admin` role in Keycloak are automatically mapped to the `Admin` role in Grafana.
