# TODO

## Zero State Admin

1. Import CML worker from AWS region by AMI name: add btn in "CML Workers" view next to "Refresh" btn.



2025-11-16 22:55:26,463 - neuroglia.mediation.tracing_middleware - DEBUG - ✅ Query 'GetCMLWorkerResourcesQuery' completed in 1421.29ms

INFO:     151.101.64.223:23449 - "GET /api/workers/region/us-east-1/workers/78ceebfa-e1bb-4678-ad59-d73d2344c7ee/resources?start_time=10m HTTP/1.1" 200 OK

2025-11-16 22:55:28,118 - neuroglia.mediation.mediator - INFO - 🔍 MEDIATOR DEBUG: Starting execute_async for request: GetCMLWorkerByIdQuery

2025-11-16 22:55:28,119 - neuroglia.mediation.mediator - DEBUG - 🔍 MEDIATOR DEBUG: Successfully resolved GetCMLWorkerByIdQueryHandler from registry

2025-11-16 22:55:28,120 - neuroglia.mediation.mediator - DEBUG - Found 3 pipeline behaviors for GetCMLWorkerByIdQuery

2025-11-16 22:55:28,124 - application.queries.get_cml_worker_by_id_query - ERROR - Error retrieving CML worker: 'CMLWorkerState' object has no attribute 'cpu_utilization'

Traceback (most recent call last):

  File "/app/src/application/queries/get_cml_worker_by_id_query.py", line 77, in handle_async

    "cpu_utilization": worker.state.cpu_utilization,

                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

AttributeError: 'CMLWorkerState' object has no attribute 'cpu_utilization'

2025-11-16 22:55:28,126 - neuroglia.mediation.metrics_middleware - DEBUG - 📊 CQRS Metrics - query.GetCMLWorkerByIdQuery: ❌ 5.41ms

2025-11-16 22:55:28,126 - neuroglia.mediation.tracing_middleware - DEBUG - ✅ Query 'GetCMLWorkerByIdQuery' completed in 5.97ms

INFO:     151.101.64.223:23449 - "GET /api/workers/region/us-east-1/workers/78ceebfa-e1bb-4678-ad59-d73d2344c7ee HTTP/1.1" 500 Internal Server Error
