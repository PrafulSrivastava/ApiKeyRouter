# Quick Start: Proving ApiKeyRouter Value

This guide shows you how to quickly run tests that prove ApiKeyRouter is better than calling LLMs directly.

## 5-Minute Demo

### Step 1: Run All Comparison Tests

```bash
cd packages/core
poetry run pytest tests/comparison/ -v -s
```

This runs 7 tests demonstrating different advantages.

### Step 2: Review Key Metrics

After running, look for these metrics in the output:

#### 💰 Cost Savings
```
📊 Cost Comparison:
  Direct approach: $0.0300 (10 requests)
  Router approach: $0.0200 (10 requests)
```
**→ Router saved 33% on costs**

#### 🛡️ Reliability
```
🛡️ Reliability Comparison:
  Direct approach: 14/20 succeeded (70.0%)
  Router approach: 20/20 succeeded (100.0%)
```
**→ Router maintained 100% uptime through failover**

#### ⚖️ Load Balancing
```
⚖️ Load Balancing Comparison:
  Router approach: Distributed across 5 keys
    Key abc12345...: 20 requests (20.0%)
    Key def67890...: 20 requests (20.0%)
```
**→ Router prevents single key overload**

### Step 3: Generate Report

```bash
python tests/comparison/run_comparison_tests.py --save-report
```

This creates a JSON report with all metrics.

## What Each Test Proves

| Test | What It Proves | Key Metric |
|------|----------------|------------|
| Cost Optimization | Router selects cheapest keys automatically | 20-40% cost savings |
| Reliability | Automatic failover when keys fail | 100% uptime maintained |
| Load Balancing | Fair distribution across keys | Even distribution (low std dev) |
| Budget Enforcement | Prevents overspending | Stays within budget limit |
| Quota Awareness | Prevents quota exhaustion | Routes away from exhausted keys |
| Performance | Minimal overhead | < 50ms routing overhead |
| Comprehensive | All advantages combined | Better overall experience |

## Real-World Validation

### Option 1: Quick Validation (5 minutes)
```bash
# Run all tests
poetry run pytest tests/comparison/ -v -s
```

### Option 2: Detailed Analysis (30 minutes)
```bash
# Run with detailed output
python tests/comparison/run_comparison_tests.py --detailed --save-report

# Review report
cat tests/comparison/comparison_report_*.json
```

### Option 3: Production Validation (Extended)
1. Set up router with real API keys
2. Run tests for extended period (hours/days)
3. Compare actual costs and reliability
4. Generate reports showing real savings

## Key Takeaways

✅ **Cost Savings**: Router automatically optimizes costs by selecting cheaper keys

✅ **Reliability**: Automatic failover ensures 100% uptime even when keys fail

✅ **Load Balancing**: Fair distribution prevents single key overload

✅ **Budget Protection**: Proactive budget enforcement prevents overspending

✅ **Quota Management**: Prevents quota exhaustion through intelligent routing

✅ **Performance**: Minimal overhead (< 50ms) for significant benefits

## Next Steps

1. **Run the tests** to see the advantages
2. **Review the metrics** that matter to your use case
3. **Customize tests** for your specific scenario
4. **Share results** with stakeholders

For detailed documentation, see [README.md](README.md).

