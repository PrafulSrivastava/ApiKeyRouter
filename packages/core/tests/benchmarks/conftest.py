"""Pytest configuration for benchmark tests."""



def pytest_configure(config):
    """Configure pytest for benchmarks."""
    # Register benchmark marker if not already registered
    config.addinivalue_line(
        "markers", "benchmark: Performance benchmark tests"
    )

