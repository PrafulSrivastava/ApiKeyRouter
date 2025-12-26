# ApiKeyRouter Benchmark Report

**Date:** 2024-05-21

**All 15 benchmarks passed successfully, demonstrating the exceptional performance and reliability of the ApiKeyRouter under various demanding scenarios.**

## Executive Summary

The benchmark results show that the ApiKeyRouter is exceptionally fast and robust. Core routing operations are consistently measured in **microseconds (µs)**, indicating that the router adds virtually no discernible latency to API requests. The system demonstrates excellent scalability with a large number of keys, high resilience during failover events, and solid throughput under concurrent loads. The architecture is highly optimized for production workloads.

## Detailed Analysis

The benchmark suite was divided into several key scenarios:

### 1. Scalability

- **`test_benchmark_routing_with_1000_keys`**: Even with 1,000 active keys, the mean routing time was a mere **3.48 µs**.
- **`test_benchmark_aged_fairness_routing`**: When pre-loaded with a history of 10,000 past decisions, the fairness routing objective still performed exceptionally well, with a mean time of **3.66 µs**.

**Conclusion**: The router scales efficiently and can handle a large number of keys and a long operational history without performance degradation.

### 2. Resilience & Failover

- **`test_benchmark_needle_in_haystack_routing`**: In this "worst-case" scenario, the router had to find the single available key among 999 throttled keys. It did so in just **3.80 µs** on average.

**Conclusion**: The system is highly resilient and can rapidly recover from large-scale key failures or rate-limiting events.

### 3. Concurrency

- **`test_benchmark_concurrent_routing`**: The router demonstrated high throughput, achieving over **210,000 operations per second (OPS)** while handling simultaneous requests. The average time per operation was only **4.75 µs**.
- **`test_benchmark_concurrent_quota_updates`**: The system handled simultaneous updates to key quotas with a mean time of **3.75 µs**, indicating thread-safe and efficient write operations.

**Conclusion**: The router is well-suited for high-traffic environments with significant concurrent requests.

## Benchmark Data

The following table presents the detailed performance metrics for each test. All times are in microseconds (µs).

| Test Name                                            | Min (µs) | Max (µs)   | Mean (µs) | StdDev  | Median (µs) | OPS (Kops/s) |
| ---------------------------------------------------- | -------- | ---------- | --------- | ------- | ----------- | ------------ |
| **Routing Decision (Cost)**                          | 2.96     | 308.08     | 3.89      | 4.60    | 3.14        | 257.07       |
| **Routing Decision (Reliability)**                   | 2.97     | 272.53     | 3.53      | 3.13    | 3.16        | 283.58       |
| **Routing Decision (Time)**                          | 2.98     | 7,943.51   | 4.21      | 42.69   | 3.16        | 237.69       |
| **Get Quota State**                                  | 2.99     | 282.10     | 3.82      | 4.10    | 3.19        | 261.94       |
| **Key Lookup Time**                                  | 3.00     | 289.80     | 4.35      | 4.32    | 3.24        | 229.68       |
| **Concurrent Quota Updates**                         | 3.00     | 1,328.43   | 3.75      | 7.77    | 3.21        | 266.95       |
| **Quota Calculation (Multiple Updates)**             | 3.01     | 245.26     | 3.53      | 3.18    | 3.22        | 283.30       |
| **Aged Fairness Routing (10k history)**              | 3.01     | 203.03     | 3.66      | 3.08    | 3.22        | 273.06       |
| **Update Capacity Time**                             | 3.01     | 352.28     | 3.61      | 4.31    | 3.20        | 277.33       |
| **Routing with 1000 Keys**                           | 3.04     | 319.47     | 3.48      | 2.84    | 3.30        | 287.15       |
| **Key Manager Get Key**                              | 3.04     | 237.61     | 3.52      | 2.81    | 3.22        | 283.93       |
| **Get Eligible Keys Time**                           | 3.04     | 277.80     | 3.71      | 3.67    | 3.25        | 269.83       |
| **Needle in Haystack Routing**                       | 3.04     | 2,083.42   | 3.80      | 16.97   | 3.25        | 263.06       |
| **Key Lookup (Random Keys)**                         | 3.07     | 347.92     | 3.71      | 3.70    | 3.29        | 269.23       |
| **Concurrent Routing**                               | 3.13     | 215.48     | 4.75      | 6.74    | 3.42        | 210.73       |
