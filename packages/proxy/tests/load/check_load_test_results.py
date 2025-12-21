"""Script to check load test results against performance targets.

This script parses Locust CSV output and validates that performance targets
are met. Fails if targets are not achieved.

Usage:
    locust -f locustfile.py --host=http://localhost:8000 --headless \
        --users 100 --spawn-rate 10 --run-time 5m --csv=results
    
    python check_load_test_results.py results_stats.csv
"""

import csv
import sys
from pathlib import Path
from typing import Any


# Performance targets
PERFORMANCE_TARGETS = {
    "throughput_rps": 1000.0,  # Requests per second
    "p50_latency_ms": 50.0,  # 50th percentile latency in milliseconds
    "p95_latency_ms": 100.0,  # 95th percentile latency in milliseconds
    "p99_latency_ms": 200.0,  # 99th percentile latency in milliseconds
    "max_error_rate": 0.01,  # Maximum error rate (1%)
}


def parse_locust_stats(csv_file: Path) -> dict[str, Any]:
    """Parse Locust statistics CSV file.

    Args:
        csv_file: Path to Locust stats CSV file.

    Returns:
        Dictionary with parsed statistics.
    """
    stats = {
        "total_requests": 0,
        "total_failures": 0,
        "total_rps": 0.0,
        "p50_ms": 0.0,
        "p95_ms": 0.0,
        "p99_ms": 0.0,
        "avg_ms": 0.0,
        "min_ms": 0.0,
        "max_ms": 0.0,
    }

    with open(csv_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Look for "Aggregated" row (total stats)
            if row.get("Type") == "Aggregated" or row.get("Name") == "Aggregated":
                stats["total_requests"] = int(row.get("Request Count", 0))
                stats["total_failures"] = int(row.get("Failure Count", 0))
                stats["total_rps"] = float(row.get("Requests/s", 0))
                stats["p50_ms"] = float(row.get("50%", 0))
                stats["p95_ms"] = float(row.get("95%", 0))
                stats["p99_ms"] = float(row.get("99%", 0))
                stats["avg_ms"] = float(row.get("Average", 0))
                stats["min_ms"] = float(row.get("Min", 0))
                stats["max_ms"] = float(row.get("Max", 0))
                break

    return stats


def check_targets(stats: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check if performance targets are met.

    Args:
        stats: Dictionary with parsed statistics.

    Returns:
        Tuple of (all_passed, error_messages).
    """
    errors = []
    all_passed = True

    # Check throughput
    if stats["total_rps"] < PERFORMANCE_TARGETS["throughput_rps"]:
        all_passed = False
        errors.append(
            f"Throughput {stats['total_rps']:.2f} RPS < "
            f"target {PERFORMANCE_TARGETS['throughput_rps']} RPS"
        )

    # Check p50 latency
    if stats["p50_ms"] > PERFORMANCE_TARGETS["p50_latency_ms"]:
        all_passed = False
        errors.append(
            f"p50 latency {stats['p50_ms']:.2f}ms > "
            f"target {PERFORMANCE_TARGETS['p50_latency_ms']}ms"
        )

    # Check p95 latency
    if stats["p95_ms"] > PERFORMANCE_TARGETS["p95_latency_ms"]:
        all_passed = False
        errors.append(
            f"p95 latency {stats['p95_ms']:.2f}ms > "
            f"target {PERFORMANCE_TARGETS['p95_latency_ms']}ms"
        )

    # Check p99 latency
    if stats["p99_ms"] > PERFORMANCE_TARGETS["p99_latency_ms"]:
        all_passed = False
        errors.append(
            f"p99 latency {stats['p99_ms']:.2f}ms > "
            f"target {PERFORMANCE_TARGETS['p99_latency_ms']}ms"
        )

    # Check error rate
    if stats["total_requests"] > 0:
        error_rate = stats["total_failures"] / stats["total_requests"]
        if error_rate > PERFORMANCE_TARGETS["max_error_rate"]:
            all_passed = False
            errors.append(
                f"Error rate {error_rate:.2%} > "
                f"target {PERFORMANCE_TARGETS['max_error_rate']:.2%}"
            )

    return all_passed, errors


def print_summary(stats: dict[str, Any]) -> None:
    """Print summary of load test results.

    Args:
        stats: Dictionary with parsed statistics.
    """
    print("\n" + "=" * 60)
    print("Load Test Results Summary")
    print("=" * 60)
    print(f"Total Requests:     {stats['total_requests']:,}")
    print(f"Total Failures:     {stats['total_failures']:,}")
    if stats["total_requests"] > 0:
        error_rate = stats["total_failures"] / stats["total_requests"]
        print(f"Error Rate:         {error_rate:.2%}")
    print(f"Requests/Second:    {stats['total_rps']:.2f}")
    print(f"\nLatency Percentiles:")
    print(f"  p50:              {stats['p50_ms']:.2f}ms")
    print(f"  p95:              {stats['p95_ms']:.2f}ms")
    print(f"  p99:              {stats['p99_ms']:.2f}ms")
    print(f"  Average:          {stats['avg_ms']:.2f}ms")
    print(f"  Min:              {stats['min_ms']:.2f}ms")
    print(f"  Max:              {stats['max_ms']:.2f}ms")
    print("=" * 60)


def main() -> int:
    """Main entry point for load test result checker.

    Returns:
        Exit code (0 if all passed, 1 if any failed).
    """
    if len(sys.argv) < 2:
        print("Usage: check_load_test_results.py <locust_stats_csv_file>")
        return 1

    csv_file = Path(sys.argv[1])
    if not csv_file.exists():
        print(f"Error: Stats file not found: {csv_file}")
        return 1

    try:
        stats = parse_locust_stats(csv_file)
        print_summary(stats)

        all_passed, errors = check_targets(stats)

        if all_passed:
            print("\n✓ All performance targets met!")
            return 0
        else:
            print("\n✗ Some performance targets not met:")
            for error in errors:
                print(f"  - {error}")
            return 1
    except Exception as e:
        print(f"Error processing load test results: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

