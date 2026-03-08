# Flajolet-Martin Benchmark

## Overview

This repository demonstrates a simple comparison between exact distinct counting (Python `set`) and an FM-style streaming sketch (register-based Flajolet–Martin) on synthetic IP traffic. The benchmark measures runtime, throughput, memory usage, and FM estimation error at configurable checkpoints.

## Why this exists

- Show the practical trade-offs between exact counting and sketching.
- Measure real Python memory usage, elapsed time, and estimation error on the same deterministic traffic stream.
- Provide a small reproducible benchmark you can extend (different hashes, register sizes, HyperLogLog, etc.).

## Repository layout

- `main.py` — benchmark driver: traffic generation, runs both counters separately, records checkpoints, prints a tabular report.
- `exact_counter.py` — exact distinct counter using Python `set`.
- `fm_counter.py` — FM-style sketch using a bucketed register array and a fast non-cryptographic hash (`xxhash64`).
- `requirements.txt` — runtime dependencies (`xxhash`).

## Quick start

1. Create/activate the virtualenv and install dependencies (the project contains a venv in `.venv` on Windows; adjust if you use another environment):

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

2. Run the benchmark with defaults (10M requests):

```bash
.venv\Scripts\python.exe main.py --requests 10000000
```

3. For development or faster feedback, run a small test:

```bash
.venv\Scripts\python.exe main.py --requests 100000 --checkpoint-count 4
```

## Example output (summary)

From a representative run (xxHash64 enabled):

- Requests processed : 10,000,000
- Distinct pool : 300,000
- FM registers : 2,048

Measured results (final checkpoint):

- Exact distinct IPs : 299,935
- FM estimate : 299,792
- Relative error : 0.05%
- Exact time : 6.28s
- FM time : 9.47s
- Exact throughput : ~1.59M req/s
- FM throughput : ~1.06M req/s
- Exact memory : 23.5 MiB
- FM memory : 2.1 KiB
- Memory reduction : ~11,712x

## Key takeaways

- Memory: The FM sketch uses orders of magnitude less memory (KiB) compared with an in-process `set` (MiB). This is the primary production advantage of sketches.
- Accuracy: With a properly sized sketch (2,048 registers) and a good non-cryptographic hash (`xxhash64`) the relative error is tiny (sub-percent in this workload).
- Speed: In Python, raw `set.add()` is highly optimized in C. The sketch path does hashing and bit work in Python for each item; with `xxhash` the gap narrows but exact counting can still be faster in typical single-process Python. In production systems, sketches are often implemented in native code and used because of bounded memory, mergeability, and network/IO savings.
