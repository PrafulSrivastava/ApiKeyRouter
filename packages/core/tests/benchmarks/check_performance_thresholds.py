"""Script to check benchmark results against performance thresholds.

This script parses pytest-benchmark JSON output and fails if any benchmark
exceeds the defined performance targets.

Usage:
    pytest tests/benchmarks/ --benchmark-json=benchmark_results.json
    python tests/benchmarks/check_performance_thresholds.py benchmark_results.json
"""

import json
import sys
from pathlib import Path

# Performance targets in milliseconds (p95)
PERFORMANCE_TARGETS = {
    "test_benchmark_routing_decision_time": 10.0,  # p95 < 10ms
    "test_benchmark_update_capacity_time": 5.0,  # p95 < 5ms
    "test_benchmark_get_quota_state_time": 5.0,  # p95 < 5ms
    "test_benchmark_key_lookup_time": 1.0,  # p95 < 1ms
}


def parse_benchmark_results(json_file: Path) -> dict[str, float]:
    """Parse pytest-benchmark JSON output and extract p95 latencies.

    Args:
        json_file: Path to benchmark JSON output file.

    Returns:
        Dictionary mapping benchmark name to p95 latency in milliseconds.
    """
    with open(json_file) as f:
        data = json.load(f)

    results = {}
    for benchmark in data.get("benchmarks", []):
        name = benchmark.get("name", "")
        stats = benchmark.get("stats", {})
        p95 = stats.get("q95", 0)  # q95 is the 95th percentile in seconds
        p95_ms = p95 * 1000  # Convert to milliseconds
        results[name] = p95_ms

    return results


def check_thresholds(results: dict[str, float]) -> tuple[bool, list[str]]:
    """Check if any benchmark exceeds performance thresholds.

    Args:
        results: Dictionary mapping benchmark name to p95 latency in milliseconds.

    Returns:
        Tuple of (all_passed, error_messages).
    """
    errors = []
    all_passed = True

    for benchmark_name, p95_ms in results.items():
        # Find matching target (support partial name matching)
        target = None
        for target_name, target_ms in PERFORMANCE_TARGETS.items():
            if target_name in benchmark_name:
                target = target_ms
                break

        if target is None:
            # No target defined, skip
            continue

        if p95_ms > target:
            all_passed = False
            error_msg = (
                f"Benchmark '{benchmark_name}' exceeded target: " f"p95={p95_ms:.2f}ms > {target}ms"
            )
            errors.append(error_msg)

    return all_passed, errors


def main() -> int:
    """Main entry point for performance threshold checker.

    Returns:
        Exit code (0 if all passed, 1 if any failed).
    """
    if len(sys.argv) < 2:
        print("Usage: check_performance_thresholds.py <benchmark_json_file>")
        return 1

    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"Error: Benchmark results file not found: {json_file}")
        return 1

    try:
        results = parse_benchmark_results(json_file)
        all_passed, errors = check_thresholds(results)

        if all_passed:
            print("✓ All benchmarks passed performance thresholds")
            return 0
        else:
            print("✗ Some benchmarks exceeded performance thresholds:")
            for error in errors:
                print(f"  - {error}")
            return 1
    except Exception as e:
        print(f"Error processing benchmark results: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

