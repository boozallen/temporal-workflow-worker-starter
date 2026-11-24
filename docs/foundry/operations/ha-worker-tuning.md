# High Availability Worker Tuning Guide

This guide covers worker tuning strategies for achieving high availability (HA) in [Temporal](https://temporal.io/) deployments.

## Table of Contents

1. [Overview](#overview)
2. [Worker Identity and Multi-Instance Deployment](#worker-identity-and-multi-instance-deployment)
3. [Concurrency Tuning](#concurrency-tuning)
4. [Slot Suppliers and Resource Management](#slot-suppliers-and-resource-management)
5. [Graceful Shutdown](#graceful-shutdown)
6. [Health Checks and Monitoring](#health-checks-and-monitoring)
7. [Production Configuration](#production-configuration)
8. [Scaling Strategies](#scaling-strategies)

## Overview

Worker tuning is critical for HA because it ensures:
- **Task distribution** across multiple worker instances
- **Resource efficiency** without overloading individual workers
- **Graceful degradation** during failures or deployments
- **Optimal throughput** while maintaining system stability

### Key Principles

1. **Never rely on defaults** - Production requires explicit configuration
2. **Benchmark under realistic load** - Tune based on actual workload patterns
3. **Monitor continuously** - Worker tuning is an ongoing process
4. **Scale horizontally** - Multiple worker instances > single large instance

## Worker Identity and Multi-Instance Deployment

### Unique Worker Identity

Each worker instance **must** have a unique identity for proper task distribution and monitoring.

**Current Implementation:**
```python
worker_identity: str = Field(
    default="research-workflow-worker",
    description="Unique identity for this worker instance",
)
```

**Production Recommendation:**
- Use Kubernetes pod name or hostname for unique identification
- Format: `{deployment-name}-{pod-name}-{timestamp}` or `{hostname}-{pid}`
- Enables per-instance monitoring and debugging

**Configuration:**
```bash
# Kubernetes deployment
WORKER_IDENTITY=${POD_NAME:-research-worker-$(hostname)-$$}

# Docker Compose
WORKER_IDENTITY=research-worker-$(hostname)-$$(date +%s)
```

### Multi-Instance Deployment

For HA, deploy **multiple worker instances** sharing the same task queue:

```yaml
# Kubernetes example
replicaCount: 3  # Minimum 3 for HA

# Each pod gets unique identity via:
env:
  - name: WORKER_IDENTITY
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

**Benefits:**
- Automatic failover if one worker crashes
- Load distribution across instances
- Zero-downtime deployments (rolling updates)

## Concurrency Tuning

### Current Defaults

```python
max_concurrent_activities: int = 100        # Activities (I/O-bound)
max_concurrent_workflow_tasks: int = 50     # Workflow tasks (CPU-bound)
max_concurrent_local_activities: int = 200  # Local activities
max_concurrent_nexus_tasks: int = 10        # Nexus tasks
```

### Tuning Guidelines

#### 1. Activity Concurrency (`max_concurrent_activities`)

**For I/O-bound activities** (e.g., agent calls, DynamoDB operations):
- **Formula**: `CPU cores × 2-4` per worker instance
- **Research workflows**: 100-200 per instance (agent calls are I/O-bound)
- **Consider**: Network latency, external service rate limits

**Production Settings:**
```python
# For 4-core worker with I/O-bound activities
max_concurrent_activities = 200  # 4 cores × 50

# For 8-core worker
max_concurrent_activities = 400  # 8 cores × 50
```

#### 2. Workflow Task Concurrency (`max_concurrent_workflow_tasks`)

**For CPU-bound workflow execution**:
- **Formula**: `CPU cores × 1-2` per worker instance
- **Research workflows**: 50-100 per instance (workflows are lightweight)
- **Consider**: Workflow complexity, state size

**Production Settings:**
```python
# For 4-core worker
max_concurrent_workflow_tasks = 50  # 4 cores × 12.5

# For 8-core worker
max_concurrent_workflow_tasks = 100  # 8 cores × 12.5
```

#### 3. Local Activity Concurrency (`max_concurrent_local_activities`)

**For fast, local operations**:
- Typically 2-4× activity concurrency
- Research workflows: 200-400 per instance

#### 4. Nexus Task Concurrency (`max_concurrent_nexus_tasks`)

**For Nexus operations**:
- Lower concurrency (10-20 per instance)
- Research workflows: 10-20 per instance

### Resource-Based Tuning

**Calculate based on available resources:**

```python
import os

# Get CPU cores (Kubernetes limits or system)
cpu_cores = int(os.getenv("CPU_LIMIT", os.cpu_count() or 4))
memory_gb = int(os.getenv("MEMORY_LIMIT_GB", 4))

# I/O-bound activities (agent calls, DynamoDB)
max_concurrent_activities = cpu_cores * 50

# CPU-bound workflow tasks
max_concurrent_workflow_tasks = cpu_cores * 12

# Local activities (2x activities)
max_concurrent_local_activities = max_concurrent_activities * 2
```

## Slot Suppliers and Resource Management

### Slot Supplier Types

Temporal supports three slot supplier types for dynamic capacity management:

#### 1. Fixed Size (Current Implementation)

**Use when:** You can calculate exact resource requirements

```python
# Current: Fixed limits
max_concurrent_activities = 100
max_concurrent_workflow_tasks = 50
```

**Pros:** Predictable, simple
**Cons:** Doesn't adapt to load or resource availability

#### 2. Resource-Based (Recommended for HA)

**Use when:** You want dynamic adaptation to CPU/memory

```python
# Example: Target 70% CPU utilization
from temporalio.worker import ResourceBasedSlotSupplier

slot_supplier = ResourceBasedSlotSupplier(
    cpu_utilization_target=0.7,  # 70% CPU target
    memory_utilization_target=0.8,  # 80% memory target
)
```

**Pros:** Adapts to load, prevents resource exhaustion
**Cons:** More complex, requires monitoring

#### 3. Custom Slot Supplier

**Use when:** You need custom logic (e.g., rate limiting, priority queues)

```python
from temporalio.worker import SlotSupplier

class CustomSlotSupplier(SlotSupplier):
    def get_available_slots(self) -> int:
        # Custom logic based on external factors
        return calculate_available_slots()
```

### Production Recommendation

For research workflows with variable agent call durations:

1. **Start with Fixed Size** for baseline
2. **Monitor resource utilization**
3. **Migrate to Resource-Based** if CPU/memory varies significantly
4. **Use Custom** only if you need advanced control

## Graceful Shutdown

### Current Implementation

The worker in [`src/worker.py`](../../../src/worker.py) already implements graceful shutdown:

```python
# Signal handlers
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
```

### Production Enhancements

#### 1. Termination Grace Period

**Kubernetes:**
```yaml
terminationGracePeriodSeconds: 120  # 2 minutes for activity completion
```

**Docker Compose:**
```yaml
stop_grace_period: 120s
```

#### 2. Activity Completion Wait

Ensure activities complete before shutdown:

```python
async def _cleanup(self) -> None:
    """Clean up resources on worker shutdown."""
    if self.worker:
        # Wait for in-flight activities to complete
        await asyncio.sleep(5)  # Allow current tasks to finish
        await self.worker.shutdown()
```

#### 3. PreStop Hook (Kubernetes)

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 10"]  # Drain connections
```

## Health Checks and Monitoring

### Critical Metrics for HA

Monitor these metrics to ensure HA:

#### 1. Schedule To Start Latency

**Alert if:** p99 > 200ms
**Indicates:** Task backlog, insufficient workers

```python
# Prometheus query
histogram_quantile(0.99, temporal_schedule_to_start_latency_bucket)
```

#### 2. Sync Match Rate

**Alert if:** p99 < 95%
**Indicates:** Workers can't keep up with task rate

```python
# Prometheus query
rate(temporal_sync_match_total[5m]) / rate(temporal_task_scheduled_total[5m])
```

#### 3. Worker Task Slots Available

**Alert if:** p99 = 0
**Indicates:** Misconfiguration, workers at capacity

```python
# Prometheus query
temporal_worker_task_slots_available
```

#### 4. Sticky Cache Metrics

**Monitor:** Forced evictions
**Indicates:** Workflow cache pressure

```python
# Prometheus query
rate(temporal_worker_sticky_cache_forced_eviction_total[5m])
```

### Health Check Endpoints

**Current:** Metrics endpoint at `:9090/metrics`

**Recommended:** Add dedicated health endpoint:

```python
# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "worker_identity": config.worker_identity,
        "uptime": get_uptime(),
    }
```

**Kubernetes Probes:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 9090
  initialDelaySeconds: 15
  periodSeconds: 20

readinessProbe:
  httpGet:
    path: /health
    port: 9090
  initialDelaySeconds: 10
  periodSeconds: 10
```

## Production Configuration

### Environment-Specific Settings

#### Development
```bash
MAX_CONCURRENT_ACTIVITIES=50
MAX_CONCURRENT_WORKFLOW_TASKS=25
WORKER_IDENTITY=research-worker-dev
```

#### Staging
```bash
MAX_CONCURRENT_ACTIVITIES=100
MAX_CONCURRENT_WORKFLOW_TASKS=50
WORKER_IDENTITY=research-worker-staging-${POD_NAME}
```

#### Production
```bash
MAX_CONCURRENT_ACTIVITIES=200
MAX_CONCURRENT_WORKFLOW_TASKS=100
WORKER_IDENTITY=research-worker-prod-${POD_NAME}
ENABLE_TLS=true
LOG_LEVEL=INFO  # Never DEBUG in production
```

### Configuration Validation

The worker already validates production config:

```python
def validate_production_config(self) -> None:
    """Validate configuration for production deployment."""
    if not self.is_production:
        return
    
    errors = []
    # Production checks...
```

**Run validation on startup:**
```python
if config.is_production:
    config.validate_production_config()
```

## Scaling Strategies

### Horizontal Scaling (Recommended)

**Deploy multiple worker instances:**

```yaml
# Kubernetes
replicaCount: 3  # Start with 3, scale based on metrics

# Auto-scaling based on task queue depth
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

**Benefits:**
- Automatic failover
- Load distribution
- Zero-downtime deployments

### Vertical Scaling

**Increase per-instance concurrency:**

```bash
# For larger instances (8 cores, 16GB)
MAX_CONCURRENT_ACTIVITIES=400
MAX_CONCURRENT_WORKFLOW_TASKS=100
```

**Trade-offs:**
- Single point of failure
- Less efficient resource utilization
- Harder to scale dynamically

### Hybrid Approach (Best for HA)

**Combine horizontal + vertical:**

1. **Multiple instances** (3+ for HA)
2. **Moderate per-instance concurrency** (100-200 activities)
3. **Auto-scaling** based on metrics

## Best Practices Summary

1. ✅ **Unique worker identity** per instance
2. ✅ **Multiple worker instances** (minimum 3 for HA)
3. ✅ **Tune concurrency** based on workload (I/O vs CPU-bound)
4. ✅ **Monitor critical metrics** (schedule-to-start, sync match rate)
5. ✅ **Graceful shutdown** with adequate termination grace period
6. ✅ **Health checks** for Kubernetes liveness/readiness
7. ✅ **Resource-based slot suppliers** for dynamic adaptation
8. ✅ **Benchmark under realistic load** before production
9. ✅ **Continuous monitoring** and adjustment
10. ✅ **Horizontal scaling** over vertical scaling

## Troubleshooting

### High Schedule To Start Latency

**Symptoms:** p99 > 200ms
**Causes:**
- Insufficient workers
- Low concurrency limits
- Network issues

**Solutions:**
- Increase worker replicas
- Increase `max_concurrent_activities`
- Check network connectivity

### Low Sync Match Rate

**Symptoms:** p99 < 95%
**Causes:**
- Workers at capacity
- Task rate exceeds worker capacity

**Solutions:**
- Scale out (more workers)
- Scale up (higher concurrency)
- Optimize activity execution time

### Worker Task Slots at Zero

**Symptoms:** `temporal_worker_task_slots_available = 0`
**Causes:**
- Misconfigured concurrency limits
- Resource exhaustion

**Solutions:**
- Review concurrency settings
- Check CPU/memory usage
- Consider resource-based slot suppliers

## References

- [Temporal Worker Tuning Guide](https://temporal.io/blog/an-introduction-to-worker-tuning)
- [Temporal High Availability](https://docs.temporal.io/cloud/high-availability)
- [Worker Performance](https://docs.temporal.io/develop/worker-performance)
- [Worker Deployment Best Practices](https://docs.temporal.io/best-practices/worker)
- [Worker Health Monitoring](https://docs.temporal.io/production-deployment/cloud/worker-health)
