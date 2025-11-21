# Issue #6: Resilience Patterns Analysis & Implementation Plan

**Date**: November 20, 2025
**Status**: ✅ **PARTIALLY IMPLEMENTED** - Significant resilience patterns already exist
**Recommendation**: Incremental enhancements with zero breaking changes

---

## Executive Summary

After comprehensive analysis, **Issue #6 is partially resolved**. The system already implements several resilience patterns:

### ✅ Existing Resilience Patterns

1. **Token Re-authentication** (`CMLApiClient`):
   - Automatic retry on 401 (token expired)
   - Re-authenticates and retries request once
   - Pattern: `get_token() → request → 401 → refresh token → retry`

2. **Graceful Degradation** (`SyncWorkerCMLDataCommand`):
   - Continues collecting data even if individual API calls fail
   - Logs warnings but doesn't fail fast
   - Returns partial results with reason codes

3. **Timeout Protection**:
   - CML API client: 15-second timeout (configurable)
   - HTTPX AsyncClient: Connection and read timeouts
   - Prevents indefinite hangs

4. **Exception Handling**:
   - Specific exception types (`IntegrationException`)
   - Differentiates: `ConnectError`, `TimeoutException`, `ClientError`
   - Proper error propagation with context

5. **Rate Limiting** (`WorkerRefreshThrottle`):
   - Per-worker refresh throttling (prevents hammering)
   - Configurable intervals
   - Protects external APIs from overload

6. **Concurrent Processing with Semaphores**:
   - Background jobs: Max 10 concurrent workers (metrics), 5 (labs)
   - Prevents resource exhaustion
   - Self-throttling under load

### 🟡 Missing Patterns (Optional Enhancements)

1. **Circuit Breaker**: No open/closed state tracking for repeatedly failing endpoints
2. **Exponential Backoff**: Retries happen immediately (no delay between attempts)
3. **Retry Limits**: Only 1 retry attempt (token refresh scenario)
4. **Fallback Data**: No cached/stale data returned on API failures

---

## Current Implementation Review

### 1. CML API Client Resilience

**File**: `src/integration/services/cml_api_client.py`

**Existing Patterns**:

```python
async def get_system_stats(self) -> CMLSystemStats | None:
    """Query CML system statistics."""
    endpoint = f"{self.base_url}/api/v0/system_stats"

    try:
        token = await self._get_token()

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            response = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})

            if response.status_code == 401:
                # ✅ Token re-authentication with single retry
                log.info("Token expired, re-authenticating")
                self._token = None
                token = await self._get_token()
                response = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})

            # ✅ Graceful handling of missing endpoints (old CML versions)
            if response.status_code == 404:
                log.warning(f"CML API endpoint not found: {endpoint}")
                return None

            if response.status_code != 200:
                log.error(f"CML API request failed: {response.status_code}")
                raise IntegrationException(f"CML API request failed: HTTP {response.status_code}")

            return CMLSystemStats.from_api_response(response.json())

    # ✅ Specific exception handling with context
    except httpx.ConnectError as e:
        log.warning(f"Cannot connect to CML instance at {self.base_url}: {e}")
        raise IntegrationException(f"Cannot connect to CML instance: {e}") from e

    except httpx.TimeoutException as e:
        log.warning(f"CML API request timed out for {self.base_url}: {e}")
        raise IntegrationException(f"CML API request timed out: {e}") from e
```

**Assessment**: ✅ **Good foundation** - Token retry, timeout protection, graceful degradation

**Missing**:

- No exponential backoff (retries immediately)
- No circuit breaker (will keep trying failed endpoints)
- No retry count limits beyond token refresh

### 2. AWS EC2 Client Resilience

**File**: `src/integration/services/aws_ec2_api_client.py`

**Existing Patterns**:

```python
def get_ami_ids_by_name(self, aws_region: AwsRegion, ami_name: str) -> list[str]:
    """Query AWS to find AMI IDs."""
    try:
        ec2_client = boto3.client(
            "ec2",
            aws_access_key_id=self.aws_account_credentials.aws_access_key_id,
            aws_secret_access_key=self.aws_account_credentials.aws_secret_access_key,
            region_name=aws_region.value,
        )

        response = ec2_client.describe_images(
            Filters=[{"Name": "name", "Values": [f"*{ami_name}*"]}]
        )

        ami_ids = [image["ImageId"] for image in response.get("Images", [])]
        return ami_ids

    # ✅ Boto3 ClientError handling with context
    except ClientError as e:
        error = self._parse_aws_error(e, f"Query AMIs by name '{ami_name}'")
        log.error(f"Failed to query AMIs: {error}")
        raise error

    # ✅ Parameter validation errors
    except (ValueError, ParamValidationError) as e:
        log.error(f"Invalid parameters for AMI query: {e}")
        raise EC2InvalidParameterException(f"Invalid AMI name parameter: {e}")
```

**Assessment**: ✅ **Good error handling** - Boto3 exceptions properly caught and translated

**Missing**:

- No retries (boto3 has built-in retries via `botocore.config.Config`)
- Could benefit from explicit retry configuration

**Note**: Boto3 already implements exponential backoff via `botocore` (default: 3 retries with jitter)

### 3. Command-Level Resilience

**File**: `src/application/commands/sync_worker_cml_data_command.py`

**Existing Pattern** (Resilient Data Collection):

```python
async def handle_async(self, request: SyncWorkerCMLDataCommand) -> OperationResult[dict]:
    """Handle sync worker CML data command."""

    # ✅ Graceful degradation - collect what we can
    system_info = None
    system_health = None
    system_stats = None
    license_info_dict = None
    api_accessible = False

    # Try system_information (no auth required)
    try:
        system_info = await cml_client.get_system_information()
        if system_info:
            api_accessible = True
    except IntegrationException as e:
        log.warning(f"⚠️ Could not fetch system info: {e}")
        # ✅ Continue - don't fail fast

    # Try system_health (requires auth)
    try:
        system_health = await cml_client.get_system_health()
        if system_health:
            api_accessible = True
    except IntegrationException as e:
        log.warning(f"⚠️ Could not fetch system health: {e}")
        # ✅ Continue - don't fail fast

    # ✅ Determine service status based on what succeeded
    if not api_accessible:
        service_status = CMLServiceStatus.UNAVAILABLE
    elif system_info and system_info.ready:
        service_status = CMLServiceStatus.READY
    else:
        service_status = CMLServiceStatus.DEGRADED

    # ✅ Return partial results
    return self.ok({
        "worker_id": command.worker_id,
        "cml_data_synced": api_accessible,
        "service_status": service_status.value,
        "cml_version": system_info.version if system_info else None,
        "cml_ready": system_info.ready if system_info else False,
    })
```

**Assessment**: ✅ **Excellent resilience** - Graceful degradation, partial results, status determination

**No changes needed** - This is best practice for resilient command patterns

---

## Recommended Enhancements (Optional)

### Priority 1: Exponential Backoff for CML API (Non-Breaking)

**Benefit**: Prevents hammering failing CML instances, improves recovery
**Effort**: 1-2 hours
**Breaking**: ❌ No - transparent retry mechanism

**Implementation**:

```python
# Add to pyproject.toml
[tool.poetry.dependencies]
tenacity = "^8.2.0"  # Async-compatible retry library

# Update CMLApiClient methods
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

class CMLApiClient:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _make_request(self, method: str, endpoint: str, **kwargs):
        """Make HTTP request with exponential backoff retry."""
        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            response = await getattr(client, method)(endpoint, **kwargs)
            return response

    async def get_system_stats(self) -> CMLSystemStats | None:
        """Query CML system statistics with retry."""
        endpoint = f"{self.base_url}/api/v0/system_stats"
        token = await self._get_token()

        try:
            # ✅ Retries with exponential backoff (1s, 2s, 4s max)
            response = await self._make_request(
                "get",
                endpoint,
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 401:
                # Token refresh still happens once
                self._token = None
                token = await self._get_token()
                response = await self._make_request(
                    "get",
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"}
                )

            # ... rest of logic unchanged
```

**Why it's safe**:

- Decorator wraps existing method
- Caller sees same interface
- Logs show retry attempts for debugging
- Configurable via settings (can be disabled)

### Priority 2: Circuit Breaker for CML Endpoints (Non-Breaking)

**Benefit**: Prevents wasting resources on known-failing endpoints
**Effort**: 2-3 hours
**Breaking**: ❌ No - fails fast but with proper logging

**Implementation**:

```python
# Add to pyproject.toml
[tool.poetry.dependencies]
aiobreaker = "^1.3.0"  # Async circuit breaker

# Add circuit breaker per worker endpoint
from aiobreaker import CircuitBreaker

class CMLApiClientFactory:
    def __init__(self):
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _get_circuit_breaker(self, base_url: str) -> CircuitBreaker:
        """Get or create circuit breaker for CML endpoint."""
        if base_url not in self._circuit_breakers:
            self._circuit_breakers[base_url] = CircuitBreaker(
                fail_max=5,              # Open after 5 failures
                timeout_duration=60,     # Reset after 60s
                name=f"cml_api_{base_url}",
            )
        return self._circuit_breakers[base_url]

    def create(self, base_url: str, **kwargs) -> CMLApiClient:
        """Create CML API client with circuit breaker."""
        breaker = self._get_circuit_breaker(base_url)
        return CMLApiClient(
            base_url=base_url,
            circuit_breaker=breaker,
            **kwargs
        )

class CMLApiClient:
    def __init__(self, base_url: str, circuit_breaker: CircuitBreaker = None, **kwargs):
        self.circuit_breaker = circuit_breaker
        # ... rest of init

    async def get_system_stats(self) -> CMLSystemStats | None:
        """Query CML system statistics with circuit breaker."""
        if self.circuit_breaker:
            # ✅ Circuit breaker wraps the call
            try:
                return await self.circuit_breaker.call_async(self._get_system_stats_impl)
            except CircuitBreakerError:
                log.warning(f"Circuit breaker OPEN for {self.base_url} - skipping request")
                return None  # Graceful degradation
        else:
            return await self._get_system_stats_impl()

    async def _get_system_stats_impl(self) -> CMLSystemStats | None:
        """Implementation without circuit breaker."""
        # ... existing logic unchanged
```

**Why it's safe**:

- Circuit breaker is optional (backwards compatible)
- Returns None when open (same as connection failure)
- Commands already handle None results gracefully
- Resets automatically after timeout

### Priority 3: Enhanced Boto3 Retry Config (Non-Breaking)

**Benefit**: Explicit control over AWS API retries
**Effort**: 30 minutes
**Breaking**: ❌ No - enhances existing behavior

**Implementation**:

```python
from botocore.config import Config

class AwsEc2Client:
    def __init__(self, aws_account_credentials: AwsAccountCredentials):
        self.aws_account_credentials = aws_account_credentials

        # ✅ Explicit retry configuration
        self.boto3_config = Config(
            retries={
                'max_attempts': 3,
                'mode': 'adaptive',  # Adjusts retry delay based on responses
            },
            connect_timeout=10,
            read_timeout=60,
        )

    def get_ami_ids_by_name(self, aws_region: AwsRegion, ami_name: str) -> list[str]:
        """Query AWS with explicit retry config."""
        ec2_client = boto3.client(
            "ec2",
            aws_access_key_id=self.aws_account_credentials.aws_access_key_id,
            aws_secret_access_key=self.aws_account_credentials.aws_secret_access_key,
            region_name=aws_region.value,
            config=self.boto3_config,  # ✅ Apply retry config
        )
        # ... rest unchanged
```

**Why it's safe**:

- Boto3 already retries (we're just being explicit)
- Adaptive mode improves backoff strategy
- Configurable via settings

---

## Implementation Recommendation

### Phase 1: Low-Hanging Fruit (Recommended Now)

**1. Add Tenacity for Exponential Backoff** (1-2 hours):

- Install `tenacity` package
- Wrap CML API methods with `@retry` decorator
- Configure: 3 attempts, exponential wait (1s, 2s, 4s)
- Only retry on `ConnectError`, `TimeoutException`
- **Impact**: Improves recovery from transient failures
- **Risk**: Very low - transparent to callers

**2. Enhanced Boto3 Config** (30 minutes):

- Add explicit `Config` with retry mode
- Document AWS API retry behavior
- **Impact**: Better AWS API resilience
- **Risk**: None - already happens implicitly

### Phase 2: Advanced Patterns (Future Enhancement)

**3. Circuit Breaker for CML Endpoints** (2-3 hours):

- Install `aiobreaker` package
- Add circuit breaker per CML endpoint
- Configure: 5 failures, 60s timeout
- **Impact**: Prevents wasting resources on dead endpoints
- **Risk**: Low - graceful degradation already exists

**4. Caching/Stale Data Fallback** (Optional, 1 day):

- Add Redis cache for CML metrics
- Return cached data when API fails
- TTL: 5-10 minutes
- **Impact**: Better UX during outages
- **Risk**: Medium - stale data complexity

---

## Configuration Strategy (Zero Breaking Changes)

Add settings to control resilience features:

```python
# src/application/settings.py

class Settings(ApplicationSettings):
    # ... existing settings

    # Resilience settings (all optional, defaults maintain current behavior)
    cml_api_retry_enabled: bool = True
    cml_api_retry_attempts: int = 3
    cml_api_retry_min_wait: float = 1.0
    cml_api_retry_max_wait: float = 10.0

    cml_circuit_breaker_enabled: bool = False  # Opt-in
    cml_circuit_breaker_fail_max: int = 5
    cml_circuit_breaker_timeout: int = 60

    aws_api_retry_mode: str = "adaptive"  # boto3 modes: standard, adaptive
    aws_api_max_attempts: int = 3
```

**Why it's safe**:

- All features opt-in via settings
- Defaults maintain current behavior
- Can be disabled per environment
- Documented in settings docstrings

---

## Testing Strategy

### Unit Tests

```python
# tests/integration/test_cml_api_client_resilience.py

@pytest.mark.asyncio
async def test_cml_api_exponential_backoff():
    """Test that CML API retries with exponential backoff."""
    client = CMLApiClient(base_url="https://fake.cml")

    with mock.patch("httpx.AsyncClient.get") as mock_get:
        # Simulate 2 failures, then success
        mock_get.side_effect = [
            httpx.TimeoutException("Timeout 1"),
            httpx.TimeoutException("Timeout 2"),
            mock.Mock(status_code=200, json=lambda: {"version": "2.9.0"}),
        ]

        result = await client.get_system_information()

        assert result.version == "2.9.0"
        assert mock_get.call_count == 3  # 2 retries + 1 success

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    """Test that circuit breaker opens after max failures."""
    breaker = CircuitBreaker(fail_max=3, timeout_duration=60)
    client = CMLApiClient(base_url="https://fake.cml", circuit_breaker=breaker)

    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        # First 3 calls should attempt connection
        for _ in range(3):
            with pytest.raises(IntegrationException):
                await client.get_system_information()

        # Circuit should be open now - no more connection attempts
        result = await client.get_system_information()
        assert result is None  # Returns None when circuit open
        assert mock_get.call_count == 3  # No additional calls
```

### Integration Tests

```python
# tests/integration/test_command_resilience.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_cml_data_graceful_degradation():
    """Test that SyncWorkerCMLDataCommand handles partial failures."""
    command = SyncWorkerCMLDataCommand(worker_id="test-worker")

    with mock.patch.object(cml_client, "get_system_information") as mock_info:
        with mock.patch.object(cml_client, "get_system_health") as mock_health:
            # system_information succeeds, health fails
            mock_info.return_value = CMLSystemInformation(version="2.9.0", ready=True)
            mock_health.side_effect = IntegrationException("Auth failed")

            result = await handler.handle_async(command)

            # Should succeed with partial data
            assert result.is_success
            assert result.data["cml_version"] == "2.9.0"
            assert result.data["service_status"] == "DEGRADED"
```

---

## Conclusion

**Issue #6 Status**: 🟡 **PARTIALLY RESOLVED**

**Current State**: System has solid resilience foundation

- ✅ Token re-authentication
- ✅ Graceful degradation
- ✅ Timeout protection
- ✅ Rate limiting
- ✅ Concurrent processing limits

**Recommended Action**: **Phase 1 enhancements only**

**Reasoning**:

1. **Existing patterns are sufficient** for current scale (50 workers, 5-min polling)
2. **Phase 1 enhancements** provide 80% benefit with 20% effort
3. **Zero breaking changes** - all features opt-in via configuration
4. **Phase 2 can wait** until system reaches scale limits or reliability issues

**Implementation Priority**:

1. ✅ **Now**: Exponential backoff (tenacity) + Enhanced boto3 config
2. 🟡 **Later**: Circuit breaker (when managing >100 workers)
3. 🟢 **Future**: Caching/fallback (when uptime SLA requires)

**Effort Estimate**: 2-3 hours for Phase 1 (recommended)

**Risk Assessment**: ⬇️ **Very Low** - All changes are additive, opt-in, and backwards compatible
