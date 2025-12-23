# Comparative Tests: ApiKeyRouter vs Direct LLM Calls

This directory contains comprehensive tests that demonstrate the advantages of using ApiKeyRouter over calling LLM providers directly.

## Overview

These tests prove that ApiKeyRouter provides:
- **Cost Optimization**: Automatically routes to cheaper keys
- **Reliability**: Automatic failover when keys fail
- **Load Balancing**: Fair distribution across multiple keys
- **Budget Enforcement**: Prevents overspending proactively
- **Quota Awareness**: Prevents quota exhaustion
- **Performance**: Minimal overhead (< 50ms)
- **Multi-Objective Optimization**: Balances cost, reliability, and fairness

## Running the Tests

### Run All Comparison Tests

```bash
# From packages/core directory
cd packages/core

# Run all comparison tests
poetry run pytest tests/comparison/ -v -s

# Run specific test
poetry run pytest tests/comparison/test_router_vs_direct.py::test_cost_optimization_router_vs_direct -v -s
```

### Run with Report Generation

```bash
# Run comparison script (generates detailed report)
python tests/comparison/run_comparison_tests.py

# Save report to file
python tests/comparison/run_comparison_tests.py --save-report
```

## Test Scenarios

### 1. Cost Optimization (`test_cost_optimization_router_vs_direct`)

**What it tests:**
- Direct approach: Always uses same key (no optimization)
- Router approach: Automatically selects cheapest available key

**Expected results:**
- Router saves 20-40% on costs compared to direct calls
- Router considers cost when selecting keys

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_cost_optimization_router_vs_direct -v -s
```

### 2. Reliability - Automatic Failover (`test_reliability_automatic_failover`)

**What it tests:**
- Direct approach: Fails completely when key fails (no fallback)
- Router approach: Automatically switches to backup key

**Expected results:**
- Router maintains 100% success rate even when some keys fail
- Direct approach fails when primary key fails

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_reliability_automatic_failover -v -s
```

### 3. Load Balancing (`test_load_balancing_fairness`)

**What it tests:**
- Direct approach: Always uses same key (uneven load)
- Router approach: Distributes load fairly across keys

**Expected results:**
- Router distributes requests evenly across multiple keys
- Direct approach overloads single key

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_load_balancing_fairness -v -s
```

### 4. Budget Enforcement (`test_budget_enforcement_prevents_overspend`)

**What it tests:**
- Direct approach: No budget control, can overspend
- Router approach: Enforces budget, rejects requests that would exceed limit

**Expected results:**
- Router prevents overspending (stays within budget)
- Direct approach can exceed budget with no protection

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_budget_enforcement_prevents_overspend -v -s
```

### 5. Quota Awareness (`test_quota_awareness_prevents_exhaustion`)

**What it tests:**
- Direct approach: No quota tracking, can exhaust keys
- Router approach: Tracks quota, routes away from exhausted keys

**Expected results:**
- Router prevents quota exhaustion by routing to available keys
- Direct approach can exhaust keys without awareness

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_quota_awareness_prevents_exhaustion -v -s
```

### 6. Performance Overhead (`test_performance_overhead_minimal`)

**What it tests:**
- Direct approach: Direct API call latency
- Router approach: Router overhead + API call latency

**Expected results:**
- Router overhead < 50ms (target from architecture)
- Minimal performance impact from routing logic

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_performance_overhead_minimal -v -s
```

### 7. Comprehensive Comparison (`test_comprehensive_comparison`)

**What it tests:**
- Real-world usage with multiple objectives combined
- Direct approach: Manual management, no optimization
- Router approach: Automatic optimization across all dimensions

**Expected results:**
- Router provides better overall experience
- Demonstrates all advantages working together

**How to verify:**
```bash
poetry run pytest tests/comparison/test_router_vs_direct.py::test_comprehensive_comparison -v -s
```

## Interpreting Results

### Cost Savings

Look for output like:
```
📊 Cost Comparison:
  Direct approach: $0.0300 (10 requests)
  Router approach: $0.0200 (10 requests)
```

**Interpretation:** Router saved 33% on costs by selecting cheaper keys.

### Reliability Improvement

Look for output like:
```
🛡️ Reliability Comparison:
  Direct approach: 14/20 succeeded (70.0%)
  Router approach: 20/20 succeeded (100.0%)
```

**Interpretation:** Router maintained 100% success rate through automatic failover.

### Load Distribution

Look for output like:
```
⚖️ Load Balancing Comparison:
  Direct approach: All 100 requests to single key
  Router approach: Distributed across 5 keys
    Key abc12345...: 20 requests (20.0%)
    Key def67890...: 20 requests (20.0%)
    ...
```

**Interpretation:** Router distributed load evenly, preventing single key overload.

### Budget Protection

Look for output like:
```
💰 Budget Enforcement Comparison:
  Budget limit: $0.50
  Direct approach: $0.75 spent (15 requests, 0 rejected)
  Router approach: $0.48 spent (12 requests, 3 rejected)
```

**Interpretation:** Router prevented overspending by rejecting requests that would exceed budget.

## Real-World Testing

For production validation, you can:

1. **Use Real API Keys**: Replace mock clients with real provider adapters
2. **Run Extended Tests**: Run tests for hours/days to see long-term benefits
3. **Measure Actual Costs**: Track real spending with and without router
4. **Monitor Reliability**: Compare uptime and error rates
5. **Load Testing**: Use tools like Locust to simulate high traffic

### Example: Real API Key Test

```python
# Modify test to use real API keys
router = ApiKeyRouter()
adapter = OpenAIAdapter()
router.register_provider("openai", adapter)

# Register real keys
key1 = await router.register_key("sk-real-key-1", "openai")
key2 = await router.register_key("sk-real-key-2", "openai")

# Run comparison tests with real keys
# (Be careful with costs!)
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/comparison.yml
- name: Run Comparison Tests
  run: |
    cd packages/core
    poetry run pytest tests/comparison/ -v --benchmark-only
    python tests/comparison/run_comparison_tests.py --save-report
```

## Next Steps

1. **Run the tests** to see ApiKeyRouter advantages
2. **Review the output** to understand specific benefits
3. **Customize tests** for your use case
4. **Share results** with stakeholders to demonstrate value
5. **Integrate into CI/CD** for continuous validation

## Troubleshooting

### Tests Fail with Import Errors

```bash
# Make sure you're in the right directory
cd packages/core
poetry install
```

### Mock Clients Not Working

The tests use mock clients for safety. For real testing, replace `MockDirectLLMClient` with actual provider clients.

### Performance Tests Show High Overhead

Performance tests measure routing overhead. In real scenarios with actual API calls, overhead is minimal compared to network latency.

## Contributing

When adding new comparison tests:

1. Follow the pattern in `test_router_vs_direct.py`
2. Include clear assertions about advantages
3. Add descriptive print statements
4. Document expected results in this README
5. Update the summary script if needed

