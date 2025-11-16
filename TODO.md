# TODO

## Zero State Admin

1. Import CML worker from AWS region by AMI name: add btn in "CML Workers" view next to "Refresh" btn.


## Testing CML API Integration

**Status:** ✅ Implementation Complete, ⏳ Testing Blocked (Workers Not Ready)

### Prerequisites Checklist

- [ ] CML worker instance is RUNNING
- [ ] Worker has `service_status = AVAILABLE`
- [ ] Worker has `https_endpoint` configured (not null)
- [ ] MongoDB is running (`docker-compose up mongodb`)
- [ ] Correct CML credentials in settings

### Test Commands

1. **Check worker status first:**

   ```bash
   docker-compose exec mongodb mongosh cml_cloud_manager --quiet \
     --eval "db.cml_workers.find({}, {name:1, status:1, service_status:1, https_endpoint:1, public_ip:1}).pretty()"
   ```

2. **Test specific endpoint (if you have HTTPS URL):**

   ```bash
   .venv/bin/python scripts/test_cml_api.py \
     --endpoint https://<worker-ip> \
     --username admin \
     --password <actual-password>
   ```

3. **Test by worker ID (looks up from database):**

   ```bash
   .venv/bin/python scripts/test_cml_api.py \
     --worker-id <worker-uuid> \
     --password <actual-password>
   ```

4. **Test all RUNNING workers:**

   ```bash
   .venv/bin/python scripts/test_cml_api.py \
     --test-all \
     --password <actual-password>
   ```

### What Gets Tested

- ✅ JWT authentication (`POST /api/v0/authenticate`)
- ✅ Token caching and auto-refresh on 401
- ✅ System stats endpoint (`GET /api/v0/system_stats`)
- ✅ SSL certificate handling (verify=False for self-signed)
- ✅ Parsing of compute nodes, dominfo, resource metrics
- ✅ Extraction of allocated CPUs, running nodes, total nodes

### Current Blockers

**Workers are not ready for testing:**

- Both workers have `https_endpoint: null`
- Both workers have `service_status: unavailable`
- Need CML service to complete initialization

**When workers are ready, you'll see:**

- `status: "running"`
- `service_status: "available"`
- `https_endpoint: "https://<ip-address>"`
- `public_ip: "<ip-address>"`

### Next Steps After Testing

Once testing succeeds:

- [ ] Verify RefreshWorkerMetricsCommand integration
- [ ] Check `cml_*` fields populated in worker state
- [ ] Confirm OTEL metrics show labs_count
- [ ] Test token expiration/refresh (wait 1+ hours)

---

## Future Enhancements

### UI Updates

- Display source-separated metrics in worker details modal
- Show EC2, CloudWatch, CML sections independently
- Add "Enable Detailed Monitoring" button for admins

### OTEL Metrics Enhancement

- Add more gauges for CML-specific metrics
- Track dominfo statistics (allocated CPUs, memory)
- Export to Prometheus/Grafana

### Time-Series Storage (if needed)

- Implement MongoDB time-series collection
- Store historical metric samples
- Create history API endpoints
