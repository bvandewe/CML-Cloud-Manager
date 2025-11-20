"""CML API Client for querying CML REST API endpoints.

This client interacts with the CML REST API running on worker instances
to collect application-level metrics and system information.

API Documentation: https://developer.cisco.com/docs/modeling-labs/
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from integration.exceptions import IntegrationException

if TYPE_CHECKING:
    from neuroglia.hosting.web import WebApplicationBuilder

log = logging.getLogger(__name__)


@dataclass
class CMLSystemInformation:
    """System information from CML API /api/v0/system_information endpoint."""

    version: str  # CML version (e.g., "2.9.0")
    ready: bool  # Whether CML is ready (has compute available)
    allow_ssh_pubkey_auth: bool  # SSH pubkey auth enabled
    oui: str | None  # OUI prefix for MAC addresses

    @classmethod
    def from_api_response(cls, data: dict) -> "CMLSystemInformation":
        """Parse CML API response into structured data.

        Args:
            data: Raw JSON response from /api/v0/system_information

        Returns:
            CMLSystemInformation instance
        """
        return cls(
            version=data.get("version", "unknown"),
            ready=data.get("ready", False),
            allow_ssh_pubkey_auth=data.get("allow_ssh_pubkey_auth", False),
            oui=data.get("oui"),
        )


@dataclass
class CMLSystemHealth:
    """System health from CML API /api/v0/system_health endpoint."""

    valid: bool  # Overall system health
    is_licensed: bool  # CML license valid
    is_enterprise: bool  # Enterprise edition
    computes: dict  # Per-compute health checks
    controller: dict  # Controller health status

    @classmethod
    def from_api_response(cls, data: dict) -> "CMLSystemHealth":
        """Parse CML API response into structured data.

        Args:
            data: Raw JSON response from /api/v0/system_health

        Returns:
            CMLSystemHealth instance
        """
        return cls(
            valid=data.get("valid", False),
            is_licensed=data.get("is_licensed", False),
            is_enterprise=data.get("is_enterprise", False),
            computes=data.get("computes", {}),
            controller=data.get("controller", {}),
        )


@dataclass
class CMLLabDetails:
    """Lab details from CML API /api/v0/labs/{lab_id} endpoint."""

    id: str
    lab_title: str
    lab_description: str
    lab_notes: str
    state: str  # STARTED, STOPPED, etc.
    owner_username: str
    owner_fullname: str
    node_count: int
    link_count: int
    created: str
    modified: str
    groups: list
    effective_permissions: list

    @classmethod
    def from_api_response(cls, data: dict) -> "CMLLabDetails":
        """Parse CML API response into structured data.

        Args:
            data: Raw JSON response from /api/v0/labs/{lab_id}

        Returns:
            CMLLabDetails instance
        """
        return cls(
            id=data.get("id", ""),
            lab_title=data.get("lab_title", "Untitled Lab"),
            lab_description=data.get("lab_description", ""),
            lab_notes=data.get("lab_notes", ""),
            state=data.get("state", "UNKNOWN"),
            owner_username=data.get("owner_username", "unknown"),
            owner_fullname=data.get("owner_fullname", "Unknown"),
            node_count=data.get("node_count", 0),
            link_count=data.get("link_count", 0),
            created=data.get("created", ""),
            modified=data.get("modified", ""),
            groups=data.get("groups", []),
            effective_permissions=data.get("effective_permissions", []),
        )


@dataclass
class CMLLicenseInfo:
    """License information from CML API /api/v0/licensing endpoint."""

    # Registration info
    registration_status: str  # COMPLETED, FAILED, etc.
    smart_account: str | None
    virtual_account: str | None
    registration_expires: str | None

    # Authorization info
    authorization_status: str  # IN_COMPLIANCE, OUT_OF_COMPLIANCE, etc.
    authorization_expires: str | None

    # Product license
    active_license: str  # CML_Enterprise, CML_Personal, etc.
    is_enterprise: bool

    # Features (licenses)
    features: list  # List of licensed features with status

    # UDI (Unique Device Identifier)
    hostname: str
    product_uuid: str

    # Full raw data for detailed modal
    raw_data: dict

    @classmethod
    def from_api_response(cls, data: dict) -> "CMLLicenseInfo":
        """Parse CML API response into structured data.

        Args:
            data: Raw JSON response from /api/v0/licensing

        Returns:
            CMLLicenseInfo instance
        """
        registration = data.get("registration", {})
        authorization = data.get("authorization", {})
        product_license = data.get("product_license", {})
        udi = data.get("udi", {})

        return cls(
            registration_status=registration.get("status", "UNKNOWN"),
            smart_account=registration.get("smart_account"),
            virtual_account=registration.get("virtual_account"),
            registration_expires=registration.get("expires"),
            authorization_status=authorization.get("status", "UNKNOWN"),
            authorization_expires=authorization.get("expires"),
            active_license=product_license.get("active", "Unknown"),
            is_enterprise=product_license.get("is_enterprise", False),
            features=data.get("features", []),
            hostname=udi.get("hostname", "unknown"),
            product_uuid=udi.get("product_uuid", "unknown"),
            raw_data=data,
        )


@dataclass
class CMLSystemStats:
    """System statistics from CML API /api/v0/system_stats endpoint."""

    # Compute nodes
    computes: dict  # Full computes data with hostname, stats, etc.

    # Aggregated stats
    all_cpu_count: int
    all_cpu_percent: float
    all_memory_total: int
    all_memory_free: int
    all_memory_used: int
    all_disk_total: int
    all_disk_free: int
    all_disk_used: int

    # Controller disk stats
    controller_disk_total: int
    controller_disk_free: int
    controller_disk_used: int

    # Derived metrics
    allocated_cpus: int = 0
    allocated_memory: int = 0
    total_nodes: int = 0
    running_nodes: int = 0

    @classmethod
    def from_api_response(cls, data: dict) -> "CMLSystemStats":
        """Parse CML API response into structured data.

        Args:
            data: Raw JSON response from /api/v0/system_stats

        Returns:
            CMLSystemStats instance
        """
        all_stats = data.get("all", {})
        controller_stats = data.get("controller", {})
        computes = data.get("computes", {})

        # Extract dominfo from first compute node (controller)
        allocated_cpus = 0
        allocated_memory = 0
        total_nodes = 0
        running_nodes = 0

        for compute_id, compute_data in computes.items():
            dominfo = compute_data.get("stats", {}).get("dominfo", {})
            if dominfo:
                allocated_cpus += dominfo.get("allocated_cpus", 0)
                allocated_memory += dominfo.get("allocated_memory", 0)
                total_nodes += dominfo.get("total_nodes", 0)
                running_nodes += dominfo.get("running_nodes", 0)

        return cls(
            computes=computes,
            all_cpu_count=all_stats.get("cpu", {}).get("count", 0),
            all_cpu_percent=all_stats.get("cpu", {}).get("percent", 0.0),
            all_memory_total=all_stats.get("memory", {}).get("total", 0),
            all_memory_free=all_stats.get("memory", {}).get("free", 0),
            all_memory_used=all_stats.get("memory", {}).get("used", 0),
            all_disk_total=all_stats.get("disk", {}).get("total", 0),
            all_disk_free=all_stats.get("disk", {}).get("free", 0),
            all_disk_used=all_stats.get("disk", {}).get("used", 0),
            controller_disk_total=controller_stats.get("disk", {}).get("total", 0),
            controller_disk_free=controller_stats.get("disk", {}).get("free", 0),
            controller_disk_used=controller_stats.get("disk", {}).get("used", 0),
            allocated_cpus=allocated_cpus,
            allocated_memory=allocated_memory,
            total_nodes=total_nodes,
            running_nodes=running_nodes,
        )


class CMLApiClient:
    """Client for CML REST API endpoints.

    Handles JWT authentication and requests to CML worker instances.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ):
        """Initialize CML API client.

        Args:
            base_url: Base URL of CML instance (e.g., "https://cml-worker.example.com")
            username: CML API username (usually "admin")
            password: CML API password
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._token: str | None = None

    async def _authenticate(self) -> str:
        """Authenticate and get JWT token.

        Returns:
            JWT token string

        Raises:
            IntegrationException: On authentication failure
        """
        auth_url = f"{self.base_url}/api/v0/authenticate"

        try:
            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.post(
                    auth_url,
                    json={"username": self.username, "password": self.password},
                )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authentication failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authentication failed: Invalid credentials"
                    )

                if response.status_code != 200:
                    log.error(
                        f"CML API auth request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API auth request failed: HTTP {response.status_code}"
                    )

                # Response is the JWT token as a string
                token = response.json()
                if not token:
                    raise IntegrationException("CML API returned empty token")

                log.debug(f"Successfully authenticated to CML at {self.base_url}")
                return token

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API auth request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API auth request timed out: {e}") from e

        except Exception as e:
            log.error(
                f"Unexpected error during CML authentication at {self.base_url}: {e}"
            )
            raise IntegrationException(f"Unexpected CML API auth error: {e}") from e

    async def _get_token(self) -> str:
        """Get cached token or authenticate to get new one.

        Returns:
            JWT token string
        """
        if not self._token:
            self._token = await self._authenticate()
        return self._token

    async def get_system_stats(self) -> CMLSystemStats | None:
        """Query CML system statistics.

        Returns:
            CMLSystemStats with system information, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/system_stats"

        try:
            # Get JWT token
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()

                    # Retry with new token
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authorization failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authorization failed: Invalid token"
                    )

                if response.status_code == 404:
                    log.warning(
                        f"CML API endpoint not found: {endpoint} (CML may be older version)"
                    )
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return CMLSystemStats.from_api_response(data)

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def get_system_health(self) -> CMLSystemHealth | None:
        """Query CML system health status.

        This endpoint requires authentication.

        Returns:
            CMLSystemHealth with health checks, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/system_health"

        try:
            # Get JWT token
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()

                    # Retry with new token
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authorization failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authorization failed: Invalid token"
                    )

                if response.status_code == 404:
                    log.warning(
                        f"CML API endpoint not found: {endpoint} (CML may be older version)"
                    )
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return CMLSystemHealth.from_api_response(data)

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def get_system_information(self) -> CMLSystemInformation | None:
        """Query CML system information (version, ready state).

        This endpoint does NOT require authentication.

        Returns:
            CMLSystemInformation with version and ready state, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/system_information"

        try:
            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(endpoint)

                if response.status_code == 404:
                    log.warning(
                        f"CML API endpoint not found: {endpoint} (CML may be older version)"
                    )
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return CMLSystemInformation.from_api_response(data)

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def health_check(self) -> bool:
        """Check if CML API is reachable.

        Returns:
            True if API responds, False otherwise
        """
        try:
            info = await self.get_system_information()
            return info is not None
        except IntegrationException:
            return False

    async def get_labs(self, show_all: bool = True) -> list[str] | None:
        """Query CML for list of lab IDs.

        This endpoint requires authentication.

        Args:
            show_all: Include all labs (default True)

        Returns:
            List of lab IDs, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs"
        params = {"show_all": "true" if show_all else "false"}

        try:
            # Get JWT token
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()

                    # Retry with new token
                    response = await client.get(
                        endpoint,
                        headers={"Authorization": f"Bearer {token}"},
                        params=params,
                    )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authorization failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authorization failed: Invalid token"
                    )

                if response.status_code == 404:
                    log.warning(
                        f"CML API endpoint not found: {endpoint} (CML may be older version)"
                    )
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return data if isinstance(data, list) else []

        except IntegrationException:
            # Re-raise IntegrationException without wrapping
            raise

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except (ValueError, TypeError) as e:
            log.error(f"Invalid JSON response from CML API at {self.base_url}: {e}")
            raise IntegrationException(
                f"Invalid JSON response from CML API: {e}"
            ) from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def get_lab_details(self, lab_id: str) -> CMLLabDetails | None:
        """Query CML for details of a specific lab.

        This endpoint requires authentication.

        Args:
            lab_id: The lab UUID

        Returns:
            CMLLabDetails with lab information, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}"

        try:
            # Get JWT token
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()

                    # Retry with new token
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authorization failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authorization failed: Invalid token"
                    )

                if response.status_code == 404:
                    log.warning(f"Lab {lab_id} not found")
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return CMLLabDetails.from_api_response(data)

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def get_licensing(self) -> CMLLicenseInfo | None:
        """Query CML licensing information.

        This endpoint requires authentication and returns Smart Licensing status,
        registration, authorization, features, and UDI information.

        Returns:
            CMLLicenseInfo with licensing details, or None if unavailable

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/licensing"

        try:
            # Get JWT token
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()

                    # Retry with new token
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code == 401 or response.status_code == 403:
                    log.error(f"CML API authorization failed for {self.base_url}")
                    raise IntegrationException(
                        "CML API authorization failed: Invalid token"
                    )

                if response.status_code == 404:
                    log.warning(
                        f"CML API endpoint not found: {endpoint} (CML may be older version)"
                    )
                    return None

                if response.status_code != 200:
                    log.error(
                        f"CML API request failed: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"CML API request failed: HTTP {response.status_code}"
                    )

                data = response.json()
                return CMLLicenseInfo.from_api_response(data)

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except Exception as e:
            log.error(f"Unexpected error querying CML API at {self.base_url}: {e}")
            raise IntegrationException(f"Unexpected CML API error: {e}") from e

    async def start_lab(self, lab_id: str) -> bool:
        """Start all nodes in a lab.

        Args:
            lab_id: Lab identifier

        Returns:
            True if operation succeeded

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}/start"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.put(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.put(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code not in [200, 204]:
                    log.error(
                        f"Failed to start lab {lab_id}: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to start lab: HTTP {response.status_code}"
                    )

                log.info(f"Successfully started lab {lab_id}")
                return True

        except Exception as e:
            log.error(f"Error starting lab {lab_id}: {e}")
            raise IntegrationException(f"Error starting lab: {e}") from e

    async def stop_lab(self, lab_id: str) -> bool:
        """Stop all nodes in a lab.

        Args:
            lab_id: Lab identifier

        Returns:
            True if operation succeeded

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}/stop"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.put(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.put(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code not in [200, 204]:
                    log.error(
                        f"Failed to stop lab {lab_id}: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to stop lab: HTTP {response.status_code}"
                    )

                log.info(f"Successfully stopped lab {lab_id}")
                return True

        except Exception as e:
            log.error(f"Error stopping lab {lab_id}: {e}")
            raise IntegrationException(f"Error stopping lab: {e}") from e

    async def wipe_lab(self, lab_id: str) -> bool:
        """Wipe all nodes in a lab (factory reset).

        Args:
            lab_id: Lab identifier

        Returns:
            True if operation succeeded

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}/wipe"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.put(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.put(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code not in [200, 204]:
                    log.error(
                        f"Failed to wipe lab {lab_id}: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to wipe lab: HTTP {response.status_code}"
                    )

                log.info(f"Successfully wiped lab {lab_id}")
                return True

        except Exception as e:
            log.error(f"Error wiping lab {lab_id}: {e}")
            raise IntegrationException(f"Error wiping lab: {e}") from e

    async def download_lab(self, lab_id: str) -> str:
        """Download lab topology as YAML.

        Args:
            lab_id: Lab identifier

        Returns:
            YAML string containing lab topology

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}/download"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code != 200:
                    log.error(
                        f"Failed to download lab {lab_id}: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to download lab: HTTP {response.status_code}"
                    )

                log.info(f"Successfully downloaded lab {lab_id}")
                return response.text

        except Exception as e:
            log.error(f"Error downloading lab {lab_id}: {e}")
            raise IntegrationException(f"Error downloading lab: {e}") from e

    async def import_lab(self, yaml_content: str, title: str | None = None) -> dict:
        """Import a lab from YAML topology.

        Args:
            yaml_content: Lab topology in CML2 YAML format
            title: Optional title for the imported lab (overrides title in YAML)

        Returns:
            Dict with lab_id of the imported lab

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/import"
        if title:
            endpoint = f"{endpoint}?title={title}"

        try:
            token = await self._get_token()

            # CML expects application/json content type with YAML as string payload
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.post(
                    endpoint, content=yaml_content, headers=headers
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    headers["Authorization"] = f"Bearer {token}"
                    response = await client.post(
                        endpoint, content=yaml_content, headers=headers
                    )

                if response.status_code != 200:
                    log.error(
                        f"Failed to import lab: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to import lab: HTTP {response.status_code}"
                    )

                result = response.json()
                log.info(f"Successfully imported lab: {result.get('id')}")
                return result

        except Exception as e:
            log.error(f"Error importing lab: {e}")
            raise IntegrationException(f"Error importing lab: {e}") from e

    async def delete_lab(self, lab_id: str) -> bool:
        """Delete a lab.

        Args:
            lab_id: Lab identifier

        Returns:
            True if deletion succeeded

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/labs/{lab_id}"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.delete(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.delete(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code not in [200, 204]:
                    log.error(
                        f"Failed to delete lab {lab_id}: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to delete lab: HTTP {response.status_code}"
                    )

                log.info(f"Successfully deleted lab {lab_id}")
                return True

        except Exception as e:
            log.error(f"Error deleting lab {lab_id}: {e}")
            raise IntegrationException(f"Error deleting lab: {e}") from e

    async def get_telemetry_events(self) -> list[dict]:
        """Fetch telemetry events from CML worker.

        This endpoint returns ALL telemetry events - there are no filtering parameters.
        The full event history is returned on every call.

        Endpoint: GET /api/v0/telemetry/events

        Returns:
            List of event objects with category, timestamp, and data

        Raises:
            IntegrationException: On API errors
        """
        endpoint = f"{self.base_url}/api/v0/telemetry/events"

        try:
            token = await self._get_token()

            async with httpx.AsyncClient(
                verify=self.verify_ssl, timeout=self.timeout
            ) as client:
                response = await client.get(
                    endpoint, headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 401:
                    # Token expired, re-authenticate
                    log.info("Token expired for telemetry events, re-authenticating")
                    self._token = None
                    token = await self._get_token()
                    response = await client.get(
                        endpoint, headers={"Authorization": f"Bearer {token}"}
                    )

                if response.status_code != 200:
                    log.error(
                        f"Failed to get telemetry events: {response.status_code} {response.text}"
                    )
                    raise IntegrationException(
                        f"Failed to get telemetry events: HTTP {response.status_code}"
                    )

                events = response.json()
                log.debug(f"Retrieved {len(events)} telemetry events")
                return events

        except IntegrationException:
            # Re-raise IntegrationException without wrapping
            raise

        except httpx.ConnectError as e:
            log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
            raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

        except httpx.TimeoutException as e:
            log.warning(f"CML API request timed out for {self.base_url}: {e}")
            raise IntegrationException(f"CML API request timed out: {e}") from e

        except (ValueError, TypeError) as e:
            log.error(
                f"Invalid JSON response from telemetry API at {self.base_url}: {e}"
            )
            raise IntegrationException(
                f"Invalid JSON response from telemetry API: {e}"
            ) from e

        except Exception as e:
            log.error(f"Error getting telemetry events: {e}")
            raise IntegrationException(f"Error getting telemetry events: {e}") from e


class CMLApiClientFactory:
    """Factory for creating CML API client instances.

    Provides consistent configuration for CML API clients across the application.
    Each worker requires its own client instance with specific endpoint and credentials.
    """

    def __init__(
        self,
        default_username: str,
        default_password: str,
        verify_ssl: bool = False,
        timeout: float = 30.0,
    ):
        """Initialize the factory with default configuration.

        Args:
            default_username: Default CML username (typically "admin")
            default_password: Default CML password
            verify_ssl: Whether to verify SSL certificates (default False for self-signed certs)
            timeout: Default request timeout in seconds
        """
        self.default_username = default_username
        self.default_password = default_password
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    def create(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool | None = None,
        timeout: float | None = None,
    ) -> CMLApiClient:
        """Create a CML API client instance for a specific worker.

        Args:
            base_url: Base URL of the CML instance (required, worker-specific)
            username: CML username (uses default if not provided)
            password: CML password (uses default if not provided)
            verify_ssl: Override SSL verification setting
            timeout: Override timeout setting

        Returns:
            Configured CMLApiClient instance
        """
        return CMLApiClient(
            base_url=base_url,
            username=username or self.default_username,
            password=password or self.default_password,
            verify_ssl=verify_ssl if verify_ssl is not None else self.verify_ssl,
            timeout=timeout if timeout is not None else self.timeout,
        )

    @staticmethod
    def configure(builder: "WebApplicationBuilder") -> None:
        """Configure CML API client factory in the application builder.

        This method:
        1. Reads default credentials from application settings
        2. Creates a CMLApiClientFactory instance
        3. Registers the factory as a singleton in the DI container

        Args:
            builder: WebApplicationBuilder instance for service registration
        """
        from application.settings import app_settings

        log.info("🔧 Configuring CML API Client Factory...")

        # Create factory with default configuration from settings
        factory = CMLApiClientFactory(
            default_username=app_settings.cml_worker_api_username,
            default_password=app_settings.cml_worker_api_password,
            verify_ssl=False,  # CML instances typically use self-signed certificates
            timeout=30.0,
        )

        # Register as singleton in DI container
        builder.services.add_singleton(CMLApiClientFactory, singleton=factory)
        log.info("✅ CML API Client Factory registered in DI container")
