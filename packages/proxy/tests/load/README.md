# Load Testing with Locust

This directory contains Locust load tests for the ApiKeyRouter Proxy service.

## Prerequisites

Install Locust:

```bash
poetry add --group dev locust
```

Or install globally:

```bash
pip install locust
```

## Running Load Tests

### Web UI Mode (Recommended for Development)

Start the proxy service first:

```bash
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

Then run Locust with web UI:

```bash
cd packages/proxy/tests/load
locust -f locustfile.py --host=http://localhost:8000
```

Open http://localhost:8089 in your browser to access the Locust web UI.

### Headless Mode (Recommended for CI)

Run load tests without web UI:

```bash
cd packages/proxy/tests/load
locust -f locustfile.py \
    --host=http://localhost:8000 \
    --headless \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --html=report.html \
    --csv=results
```

### Run Specific Scenarios

Run only normal load tests:

```bash
locust -f locustfile.py --host=http://localhost:8000 \
    -u 50 -r 5 -t 2m --tags normal_load
```

Run high load stress tests:

```bash
locust -f locustfile.py --host=http://localhost:8000 \
    -u 200 -r 20 -t 5m --tags high_load
```

Run failure scenario tests:

```bash
locust -f locustfile.py --host=http://localhost:8000 \
    -u 20 -r 2 -t 2m --tags failure_scenario
```

## Test Scenarios

### 1. Normal Load (Baseline)

- **Purpose**: Establish baseline performance metrics
- **Users**: 50-100 concurrent users
- **Spawn Rate**: 5-10 users/second
- **Duration**: 5-10 minutes
- **Expected**: System handles load gracefully, maintains <100ms p95 latency

### 2. High Load (Stress Test)

- **Purpose**: Test system limits and behavior under stress
- **Users**: 200-500 concurrent users
- **Spawn Rate**: 20-50 users/second
- **Duration**: 5-10 minutes
- **Expected**: System may show degradation but should not crash

### 3. Failure Scenarios

- **Purpose**: Test graceful degradation and error handling
- **Users**: 20-50 concurrent users
- **Spawn Rate**: 2-5 users/second
- **Duration**: 2-5 minutes
- **Expected**: System handles errors gracefully, returns appropriate status codes

### 4. Concurrent Key Switching

- **Purpose**: Test system behavior when requests switch keys rapidly
- **Users**: 100-200 concurrent users
- **Spawn Rate**: 10-20 users/second
- **Duration**: 5 minutes
- **Expected**: System distributes load across keys efficiently

## Performance Targets

- **Throughput**: 1000+ requests/second
- **Latency (p50)**: <50ms
- **Latency (p95)**: <100ms
- **Latency (p99)**: <200ms
- **Error Rate**: <1% (excluding expected 429 rate limits)

## Interpreting Results

### Key Metrics

1. **Requests per Second (RPS)**: Total throughput
2. **Response Time (p50/p95/p99)**: Latency percentiles
3. **Failure Rate**: Percentage of failed requests
4. **Response Codes**: Distribution of HTTP status codes

### Success Criteria

- ✅ p95 latency < 100ms under normal load
- ✅ Throughput > 1000 req/s
- ✅ Error rate < 1% (excluding 429)
- ✅ System recovers after load decreases
- ✅ No memory leaks or resource exhaustion

### Failure Indicators

- ❌ p95 latency > 200ms consistently
- ❌ Throughput < 500 req/s
- ❌ Error rate > 5%
- ❌ System crashes or becomes unresponsive
- ❌ Memory usage grows unbounded

## CI Integration

Load tests can be integrated into CI/CD pipeline:

```yaml
- name: Run load tests
  run: |
    # Start proxy service in background
    poetry run uvicorn apikeyrouter_proxy.main:app &
    sleep 5
    
    # Run load tests
    cd packages/proxy/tests/load
    locust -f locustfile.py \
        --host=http://localhost:8000 \
        --headless \
        --users 100 \
        --spawn-rate 10 \
        --run-time 2m \
        --html=load_test_report.html \
        --csv=load_test_results
    
    # Check results (fail if targets not met)
    python check_load_test_results.py load_test_results_stats.csv
```

## Troubleshooting

### Proxy Service Not Running

Ensure the proxy service is running before starting Locust:

```bash
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

### Connection Refused

Check that the proxy is listening on the correct host and port:

```bash
curl http://localhost:8000/health
```

### High Error Rate

- Check proxy service logs for errors
- Verify API keys are registered
- Check system resources (CPU, memory)
- Review network connectivity

### Low Throughput

- Check system resources (CPU, memory, network)
- Review proxy service configuration
- Check for bottlenecks in routing logic
- Verify database/state store performance

## Customization

### Adding New Test Scenarios

Edit `locustfile.py` and add new task sets or user classes:

```python
class CustomScenarioUser(HttpUser):
    tasks = [CustomTasks]
    wait_time = between(1, 3)
    weight = 1
```

### Adjusting Load Parameters

Modify user classes to adjust:
- `wait_time`: Time between requests
- `weight`: Probability of selecting this user class
- Task weights: Relative frequency of tasks

## Results Storage

Locust generates several output files:

- `results_stats.csv`: Request statistics
- `results_failures.csv`: Failed requests
- `results_exceptions.csv`: Exceptions
- `report.html`: HTML report with charts

Store these files for trend analysis and comparison.

