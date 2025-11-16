"""CML API Client for querying CML REST API endpoints.

This client interacts with the CML REST API running on worker instances
to collect application-level metrics and system information.

API Documentation: https://developer.cisco.com/docs/modeling-labs/
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from integration.exceptions import IntegrationException

log = logging.getLogger(__name__)


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
        self._token: Optional[str] = None

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

    async def get_system_stats(self) -> Optional[CMLSystemStats]:
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

    async def health_check(self) -> bool:
        """Check if CML API is reachable.

        Returns:
            True if API responds, False otherwise
        """
        try:
            stats = await self.get_system_stats()
            return stats is not None
        except IntegrationException:
            return False
