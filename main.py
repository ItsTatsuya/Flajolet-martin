from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass

from exact_counter import ExactDistinctCounter
from fm_counter import FlajoletMartinDistinctCounter


def format_bytes(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(size):,} {unit}"
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GiB"


def percent_error(estimate: float, actual: int) -> float:
    if actual == 0:
        return 0.0
    return abs(estimate - actual) / actual * 100


@dataclass(frozen=True)
class ExperimentConfig:
    total_requests: int = 10_000_000
    ip_pool_size: int = 300_000
    repeat_probability: float = 0.75
    hot_pool_fraction: float = 0.05
    num_registers: int = 2048
    checkpoint_count: int = 6
    seed: int = 42


@dataclass(frozen=True)
class Snapshot:
    processed_requests: int
    exact_distinct: int
    sketch_estimate: float
    error_percent: float
    exact_elapsed_seconds: float
    sketch_elapsed_seconds: float
    exact_memory_bytes: int
    sketch_memory_bytes: int


@dataclass(frozen=True)
class CounterRunResult:
    elapsed_seconds: float
    final_value: float
    final_memory_bytes: int
    checkpoint_values: dict[int, float]
    checkpoint_elapsed_seconds: dict[int, float]
    checkpoint_memory_bytes: dict[int, int]


def generate_ip_pool(pool_size: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    unique_ips: set[str] = set()
    while len(unique_ips) < pool_size:
        unique_ips.add(
            f"{rng.randint(1, 223)}.{rng.randint(0, 255)}."
            f"{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        )
    return list(unique_ips)


def request_stream(config: ExperimentConfig, ip_pool: list[str]):
    rng = random.Random(config.seed)
    hot_pool_size = max(1, int(len(ip_pool) * config.hot_pool_fraction))
    hot_pool = ip_pool[:hot_pool_size]

    for _ in range(config.total_requests):
        if rng.random() < config.repeat_probability:
            yield rng.choice(hot_pool)
        else:
            yield rng.choice(ip_pool)


def build_checkpoints(total_requests: int, checkpoint_count: int) -> list[int]:
    checkpoints = {
        max(1, int(total_requests * index / checkpoint_count))
        for index in range(1, checkpoint_count + 1)
    }
    return sorted(checkpoints)


def benchmark_exact(
    config: ExperimentConfig, ip_pool: list[str], checkpoints: list[int]
) -> CounterRunResult:
    counter = ExactDistinctCounter()
    checkpoint_values: dict[int, float] = {}
    checkpoint_elapsed_seconds: dict[int, float] = {}
    checkpoint_memory_bytes: dict[int, int] = {}
    pending_checkpoint_index = 0
    start_time = time.perf_counter()

    for processed_requests, ip in enumerate(request_stream(config, ip_pool), start=1):
        counter.process(ip)

        if processed_requests != checkpoints[pending_checkpoint_index]:
            continue

        checkpoint_values[processed_requests] = float(counter.distinct_count())
        checkpoint_elapsed_seconds[processed_requests] = (
            time.perf_counter() - start_time
        )
        checkpoint_memory_bytes[processed_requests] = counter.memory_bytes()
        pending_checkpoint_index += 1
        if pending_checkpoint_index == len(checkpoints):
            break

    elapsed_seconds = time.perf_counter() - start_time
    return CounterRunResult(
        elapsed_seconds=elapsed_seconds,
        final_value=float(counter.distinct_count()),
        final_memory_bytes=counter.memory_bytes(),
        checkpoint_values=checkpoint_values,
        checkpoint_elapsed_seconds=checkpoint_elapsed_seconds,
        checkpoint_memory_bytes=checkpoint_memory_bytes,
    )


def benchmark_fm(
    config: ExperimentConfig, ip_pool: list[str], checkpoints: list[int]
) -> CounterRunResult:
    counter = FlajoletMartinDistinctCounter(
        num_registers=config.num_registers,
        seed=config.seed,
    )
    checkpoint_values: dict[int, float] = {}
    checkpoint_elapsed_seconds: dict[int, float] = {}
    checkpoint_memory_bytes: dict[int, int] = {}
    pending_checkpoint_index = 0
    start_time = time.perf_counter()

    for processed_requests, ip in enumerate(request_stream(config, ip_pool), start=1):
        counter.process(ip)

        if processed_requests != checkpoints[pending_checkpoint_index]:
            continue

        checkpoint_values[processed_requests] = counter.estimate()
        checkpoint_elapsed_seconds[processed_requests] = (
            time.perf_counter() - start_time
        )
        checkpoint_memory_bytes[processed_requests] = counter.memory_bytes()
        pending_checkpoint_index += 1
        if pending_checkpoint_index == len(checkpoints):
            break

    elapsed_seconds = time.perf_counter() - start_time
    return CounterRunResult(
        elapsed_seconds=elapsed_seconds,
        final_value=counter.estimate(),
        final_memory_bytes=counter.memory_bytes(),
        checkpoint_values=checkpoint_values,
        checkpoint_elapsed_seconds=checkpoint_elapsed_seconds,
        checkpoint_memory_bytes=checkpoint_memory_bytes,
    )


def run_experiment(
    config: ExperimentConfig,
) -> tuple[list[Snapshot], CounterRunResult, CounterRunResult]:
    ip_pool = generate_ip_pool(config.ip_pool_size, config.seed)
    checkpoints = build_checkpoints(config.total_requests, config.checkpoint_count)
    exact_result = benchmark_exact(config, ip_pool, checkpoints)
    fm_result = benchmark_fm(config, ip_pool, checkpoints)

    snapshots: list[Snapshot] = []
    for checkpoint in checkpoints:
        exact_distinct = int(exact_result.checkpoint_values[checkpoint])
        sketch_estimate = fm_result.checkpoint_values[checkpoint]
        snapshots.append(
            Snapshot(
                processed_requests=checkpoint,
                exact_distinct=exact_distinct,
                sketch_estimate=sketch_estimate,
                error_percent=percent_error(sketch_estimate, exact_distinct),
                exact_elapsed_seconds=exact_result.checkpoint_elapsed_seconds[
                    checkpoint
                ],
                sketch_elapsed_seconds=fm_result.checkpoint_elapsed_seconds[checkpoint],
                exact_memory_bytes=exact_result.checkpoint_memory_bytes[checkpoint],
                sketch_memory_bytes=fm_result.checkpoint_memory_bytes[checkpoint],
            )
        )

    return snapshots, exact_result, fm_result


def print_report(
    config: ExperimentConfig,
    snapshots: list[Snapshot],
    exact_result: CounterRunResult,
    fm_result: CounterRunResult,
) -> None:
    final = snapshots[-1]
    exact_throughput = config.total_requests / max(exact_result.elapsed_seconds, 1e-9)
    fm_throughput = config.total_requests / max(fm_result.elapsed_seconds, 1e-9)

    print("Distinct IP Finder")
    print(f"  Requests processed : {config.total_requests:,}")
    print(f"  Distinct IP pool   : {config.ip_pool_size:,}")
    print(f"  Repeat probability : {config.repeat_probability:.0%}")
    print(f"  Hot pool fraction  : {config.hot_pool_fraction:.0%}")
    print(f"  FM registers       : {config.num_registers:,}")
    print(f"  Random seed        : {config.seed}")

    print("\nMeasured Counter State")
    print(
        f"  {'Requests':>10} | {'Exact Distinct':>14} | {'FM Estimate':>12} | {'Error':>8} | {'Exact Time':>10} | {'FM Time':>10} | {'Exact Memory':>14} | {'FM Memory':>10}"
    )
    print(f"  {'-' * 117}")

    for snapshot in snapshots:
        print(
            f"  {snapshot.processed_requests:>10,} | "
            f"{snapshot.exact_distinct:>14,} | "
            f"{snapshot.sketch_estimate:>12,.0f} | "
            f"{snapshot.error_percent:>7.2f}% | "
            f"{snapshot.exact_elapsed_seconds:>9.2f}s | "
            f"{snapshot.sketch_elapsed_seconds:>9.2f}s | "
            f"{format_bytes(snapshot.exact_memory_bytes):>14} | "
            f"{format_bytes(snapshot.sketch_memory_bytes):>10}"
        )

    final_savings = final.exact_memory_bytes / max(final.sketch_memory_bytes, 1)
    print("\nFinal Result")
    print(f"  Exact distinct IPs : {final.exact_distinct:,}")
    print(f"  FM estimate        : {final.sketch_estimate:,.0f}")
    print(f"  Relative error     : {final.error_percent:.2f}%")
    print(f"  Exact time         : {exact_result.elapsed_seconds:.2f}s")
    print(f"  FM time            : {fm_result.elapsed_seconds:.2f}s")
    print(f"  Exact throughput   : {exact_throughput:,.0f} req/s")
    print(f"  FM throughput      : {fm_throughput:,.0f} req/s")
    print(f"  Exact memory       : {format_bytes(final.exact_memory_bytes)}")
    print(f"  FM memory          : {format_bytes(final.sketch_memory_bytes)}")
    print(f"  Memory reduction   : {final_savings:.1f}x")
    if fm_result.elapsed_seconds < exact_result.elapsed_seconds:
        print(
            f"  FM speedup         : {exact_result.elapsed_seconds / fm_result.elapsed_seconds:.2f}x faster than exact"
        )
    else:
        print(
            f"  FM slowdown        : {fm_result.elapsed_seconds / exact_result.elapsed_seconds:.2f}x slower than exact"
        )


def parse_args() -> ExperimentConfig:
    parser = argparse.ArgumentParser(
        description="Compare exact distinct IP counting with an FM-style streaming sketch."
    )
    parser.add_argument("--requests", type=int, default=10_000_000)
    parser.add_argument("--ip-pool-size", type=int, default=300_000)
    parser.add_argument("--repeat-probability", type=float, default=0.75)
    parser.add_argument("--hot-pool-fraction", type=float, default=0.05)
    parser.add_argument("--registers", type=int, default=2048)
    parser.add_argument("--checkpoint-count", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    return ExperimentConfig(
        total_requests=args.requests,
        ip_pool_size=args.ip_pool_size,
        repeat_probability=args.repeat_probability,
        hot_pool_fraction=args.hot_pool_fraction,
        num_registers=args.registers,
        checkpoint_count=args.checkpoint_count,
        seed=args.seed,
    )


def main() -> None:
    config = parse_args()
    snapshots, exact_result, fm_result = run_experiment(config)
    print_report(config, snapshots, exact_result, fm_result)


if __name__ == "__main__":
    main()
