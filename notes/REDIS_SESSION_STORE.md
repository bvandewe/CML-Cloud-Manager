# Redis Session Store for Horizontal Scaling

## Overview

The application now supports **distributed session storage** using Redis, enabling stateless deployments that can scale horizontally in Kubernetes and other container orchestration platforms.

## Architecture

### Session Store Abstraction

The `SessionStore` abstract base class defines the interface for session management:

```python
class SessionStore(ABC):
    @abstractmethod
    def create_session(self, tokens: Dict, user_info: Dict) -> str: ...

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Dict]: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> None: ...

    @abstractmethod
    def refresh_session(self, session_id: str, new_tokens: Dict) -> None: ...
```

### Two Implementations

#### 1. InMemorySessionStore (Development)

**Use Case**: Local development, testing
**Characteristics**:

- ⚡ Fast (no network overhead)
- 💾 Simple (no external dependencies)
- ⚠️ Stateful (sessions stored in process memory)
- ❌ **NOT suitable for production** (sessions lost on restart, not shared across pods)

**When to use**:

- Local development (`docker-compose up`)
- Running single instance for testing
- Quick prototyping

#### 2. RedisSessionStore (Production)

**Use Case**: Production deployments, Kubernetes
**Characteristics**:

- 🔴 Distributed (sessions stored in Redis)
- 🔄 Stateless (app pods don't store session state)
- 📈 Scalable (multiple pods can share sessions)
- 💪 Persistent (sessions survive pod restarts)
- ⏰ Auto-expiring (Redis TTL handles cleanup)

**When to use**:

- Production deployments
- Kubernetes with multiple replicas
- Load-balanced environments
- Any scenario requiring horizontal scaling

## Configuration

### Environment Variables

Add these to your `.env` file or environment:

```bash
# Redis Session Storage
REDIS_ENABLED=false           # Set to true for production
REDIS_URL=redis://redis:6379/0  # Redis connection URL
REDIS_KEY_PREFIX=session:      # Prefix for session keys in Redis
```

### Settings (src/settings.py)

```python
class Settings(BaseSettings):
    # Redis Configuration (for production session storage)
    REDIS_URL: str = "redis://redis:6379/0"  # Internal Docker network URL
    REDIS_ENABLED: bool = False  # Set to True for production with Redis
    REDIS_KEY_PREFIX: str = "session:"
```

### Docker Compose

The `docker-compose.yml` includes a Redis service:

```yaml
redis:
  image: redis:7.4-alpine
  restart: always
  ports:
    - "6379:6379"
  command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 3
```

**Redis Configuration Explained**:

- `--appendonly yes`: Enables AOF persistence (sessions survive Redis restart)
- `--maxmemory 256mb`: Limits memory usage
- `--maxmemory-policy allkeys-lru`: Evicts least recently used keys when memory is full

## How to Enable Redis

### For Docker Compose (Development/Testing)

1. **Update your `.env` file**:

   ```bash
   REDIS_ENABLED=true
   ```

2. **Restart the application**:

   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. **Verify Redis connection**:
   Check the app logs for:

   ```
   🔴 Using RedisSessionStore (url=redis://redis:6379/0)
   ✅ Redis connection successful
   ```

### For Production (Kubernetes)

1. **Deploy Redis** (various options):

   **Option A: Redis Standalone**

   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: redis
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: redis
     template:
       metadata:
         labels:
           app: redis
       spec:
         containers:
         - name: redis
           image: redis:7.4-alpine
           ports:
           - containerPort: 6379
           command:
           - redis-server
           - --appendonly yes
           - --maxmemory 256mb
           - --maxmemory-policy allkeys-lru
           volumeMounts:
           - name: redis-data
             mountPath: /data
         volumes:
         - name: redis-data
           persistentVolumeClaim:
             claimName: redis-pvc
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: redis
   spec:
     ports:
     - port: 6379
       targetPort: 6379
     selector:
       app: redis
   ```

   **Option B: Redis Sentinel (High Availability)**
   - Use Bitnami Helm chart: `helm install redis bitnami/redis`
   - Provides automatic failover
   - Multiple replicas for redundancy

   **Option C: Managed Redis**
   - AWS ElastiCache
   - Azure Cache for Redis
   - Google Cloud Memorystore
   - Digital Ocean Managed Redis

2. **Configure app deployment**:

   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: system-designer
   spec:
     replicas: 3  # Scale horizontally!
     template:
       spec:
         containers:
         - name: app
           image: system-designer:latest
           env:
           - name: REDIS_ENABLED
             value: "true"
           - name: REDIS_URL
             value: "redis://redis:6379/0"  # Or your managed Redis URL
           - name: REDIS_KEY_PREFIX
             value: "session:"
   ```

3. **Test horizontal scaling**:

   ```bash
   # Scale to 5 replicas
   kubectl scale deployment system-designer --replicas=5

   # Watch pods come up
   kubectl get pods -w

   # Test: Login and check session persists across pods
   # Multiple requests may hit different pods (load balancer)
   ```

## Session Data Structure

Sessions stored in Redis contain:

```json
{
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cC...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5...",
    "id_token": "eyJhbGciOiJSUzI1NiIsInR5cC...",
    "expires_in": 300,
    "refresh_expires_in": 1800
  },
  "user_info": {
    "sub": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "preferred_username": "admin",
    "given_name": "Admin",
    "family_name": "User"
  },
  "created_at": "2024-01-15T10:30:00",
  "expires_at": "2024-01-15T18:30:00"
}
```

**Redis Key Structure**:

- Key: `session:{session_id}` (e.g., `session:abc123def456...`)
- TTL: Automatically set to session timeout (default: 8 hours)
- Value: JSON-serialized session data

## Testing Horizontal Scaling

### Test Scenario: Multiple App Instances

1. **Start Redis and multiple app instances**:

   ```bash
   # Using docker-compose scale (for testing)
   docker-compose up -d --scale app=3
   ```

2. **Login via browser**:
   - Go to `http://localhost:8020`
   - Click "Login with Keycloak"
   - Login with test credentials (admin/test)

3. **Verify session sharing**:

   ```bash
   # Check Redis for your session
   docker-compose exec redis redis-cli
   127.0.0.1:6379> KEYS session:*
   1) "session:abcdef123456..."

   127.0.0.1:6379> TTL session:abcdef123456...
   (integer) 28799  # Remaining seconds

   127.0.0.1:6379> GET session:abcdef123456...
   "{\"tokens\": {...}, \"user_info\": {...}}"
   ```

4. **Test pod restart resilience**:

   ```bash
   # Restart one app instance
   docker-compose restart app

   # Session should persist - refresh browser, still logged in!
   ```

### Test Scenario: Kubernetes Load Balancing

1. **Deploy with multiple replicas**:

   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl get pods  # Should see 3+ pods
   ```

2. **Login and check logs**:

   ```bash
   # Login via browser
   # Watch logs from multiple pods
   kubectl logs -l app=system-designer --tail=10 -f

   # You should see:
   # - Login handled by pod-1
   # - API request handled by pod-2
   # - Another request handled by pod-3
   # All using the same session from Redis!
   ```

3. **Verify session in Redis**:

   ```bash
   # Port-forward to Redis
   kubectl port-forward svc/redis 6379:6379

   # Connect with redis-cli
   redis-cli
   127.0.0.1:6379> KEYS session:*
   ```

## Monitoring and Troubleshooting

### Health Check

The `RedisSessionStore` includes a `ping()` method:

```python
store = RedisSessionStore(redis_url="redis://localhost:6379/0")
if store.ping():
    print("✅ Redis connection healthy")
else:
    print("❌ Redis connection failed")
```

### Common Issues

#### 1. Connection Refused

**Symptom**: `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solutions**:

- Check Redis is running: `docker-compose ps redis`
- Check Redis health: `docker-compose exec redis redis-cli ping`
- Verify REDIS_URL setting matches Redis host
- Check network connectivity

#### 2. Memory Eviction

**Symptom**: Sessions disappearing unexpectedly

**Solutions**:

- Check Redis memory: `docker-compose exec redis redis-cli INFO memory`
- Increase `maxmemory` in Redis config
- Monitor evicted_keys: `redis-cli INFO stats | grep evicted_keys`

#### 3. Sessions Not Shared Across Pods

**Symptom**: User logged out after some requests (load balancer routing to different pod)

**Solutions**:

- Verify REDIS_ENABLED=true in all pods
- Check all pods using same REDIS_URL
- Verify Redis network connectivity from all pods
- Check session_id cookie is being sent (check browser dev tools)

### Redis Monitoring

**Key metrics to monitor**:

```bash
# Connection info
redis-cli CLIENT LIST

# Memory usage
redis-cli INFO memory

# Key statistics
redis-cli INFO keyspace

# Session count
redis-cli KEYS "session:*" | wc -l

# Specific session details
redis-cli GET "session:abc123..."
redis-cli TTL "session:abc123..."
```

## Performance Considerations

### Redis vs In-Memory

| Aspect | InMemorySessionStore | RedisSessionStore |
|--------|---------------------|------------------|
| **Latency** | ~0.01ms (local) | ~1-5ms (network) |
| **Throughput** | Very High | High |
| **Scalability** | ❌ Single instance only | ✅ Unlimited horizontal scaling |
| **Persistence** | ❌ Lost on restart | ✅ Survives restarts |
| **HA** | ❌ Single point of failure | ✅ Can use Redis Sentinel/Cluster |

### Optimization Tips

1. **Use Redis Pipelining** (future enhancement):

   ```python
   # Instead of:
   for session_id in session_ids:
       store.delete_session(session_id)

   # Use pipeline:
   pipe = redis_client.pipeline()
   for session_id in session_ids:
       pipe.delete(store._make_key(session_id))
   pipe.execute()
   ```

2. **Connection Pooling**: Already handled by `redis-py`
   - Default pool size: 50 connections
   - Configure with: `ConnectionPool(max_connections=100)`

3. **Compression** (optional for large sessions):

   ```python
   import gzip
   compressed = gzip.compress(json.dumps(session_data).encode())
   redis_client.set(key, compressed)
   ```

## Security Considerations

### Data in Redis

- **Sessions contain tokens**: Access tokens, refresh tokens, ID tokens
- **Sensitive user info**: Email, name, roles
- **Network security**: Use TLS for production Redis connections
- **Authentication**: Use Redis AUTH in production (`redis://user:password@host:port/db`)

### Production Security Checklist

- [ ] Enable Redis AUTH: `requirepass strong-password-here`
- [ ] Use TLS: `rediss://` (note the extra 's')
- [ ] Network isolation: Redis in private network/VPC
- [ ] Firewall rules: Only app pods can reach Redis
- [ ] Encryption at rest: Enable on managed Redis services
- [ ] Audit logs: Enable Redis slow log and monitoring

### Example Production URL

```bash
# Local development (no auth)
REDIS_URL=redis://redis:6379/0

# Production with AUTH
REDIS_URL=redis://:strong-password@redis:6379/0

# Production with TLS and AUTH
REDIS_URL=rediss://:strong-password@redis.production.internal:6379/0

# Managed service (AWS ElastiCache)
REDIS_URL=rediss://master.redis-cluster.abc123.use1.cache.amazonaws.com:6379/0
```

## Migration from In-Memory to Redis

### Zero-Downtime Migration

1. **Deploy Redis** (without enabling REDIS_ENABLED)
2. **Verify Redis health** (ping test)
3. **Enable Redis** on one instance (canary)
4. **Monitor** for errors
5. **Roll out** to all instances (REDIS_ENABLED=true)
6. **Note**: Existing sessions in memory will be lost (users logged out once)

### Gradual Migration Strategy

```python
# Optional: Dual-write pattern (write to both stores during migration)
class HybridSessionStore(SessionStore):
    def __init__(self, primary: SessionStore, secondary: SessionStore):
        self.primary = primary
        self.secondary = secondary

    def create_session(self, tokens, user_info):
        session_id = self.primary.create_session(tokens, user_info)
        try:
            self.secondary.create_session_with_id(session_id, tokens, user_info)
        except Exception as e:
            logger.warning(f"Secondary store write failed: {e}")
        return session_id

    def get_session(self, session_id):
        # Try primary first, fallback to secondary
        session = self.primary.get_session(session_id)
        if not session:
            session = self.secondary.get_session(session_id)
        return session
```

## Summary

✅ **Stateless Architecture**: App pods store no session state
✅ **Horizontal Scaling**: Scale to unlimited replicas in Kubernetes
✅ **High Availability**: Sessions survive pod restarts and crashes
✅ **Auto-Expiring**: Redis TTL handles session cleanup automatically
✅ **Production-Ready**: Battle-tested pattern used by major platforms
✅ **Flexible**: Easy to switch between in-memory (dev) and Redis (prod)

## References

- [Redis Session Store Pattern](https://redis.io/docs/manual/patterns/distributed-locks/)
- [Kubernetes StatefulSet vs Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Backend-for-Frontend (BFF) Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/backends-for-frontends)
- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
