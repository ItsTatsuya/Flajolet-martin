from __future__ import annotations

import math
import sys

import xxhash


def hash_ip(ip: str, seed: int) -> int:
    return xxhash.xxh64_intdigest(ip, seed=seed)


class FlajoletMartinDistinctCounter:
    def __init__(self, num_registers: int = 2048, seed: int = 42) -> None:
        if num_registers <= 0 or num_registers & (num_registers - 1):
            raise ValueError("num_registers must be a positive power of two")

        self.seed = seed
        self.num_registers = num_registers
        self.bucket_bits = num_registers.bit_length() - 1
        self.bucket_mask = num_registers - 1
        self.registers = bytearray(num_registers)

    def process(self, ip: str) -> None:
        hashed = hash_ip(ip, self.seed)
        bucket = hashed & self.bucket_mask
        suffix = hashed >> self.bucket_bits
        rank = self._rank(suffix)
        if rank > self.registers[bucket]:
            self.registers[bucket] = rank

    def estimate(self) -> float:
        alpha = {16: 0.673, 32: 0.697, 64: 0.709}.get(
            self.num_registers, 0.7213 / (1 + 1.079 / self.num_registers)
        )
        raw_estimate = (
            alpha
            * self.num_registers
            * self.num_registers
            / sum(2.0 ** (-rank) for rank in self.registers)
        )

        zero_registers = self.registers.count(0)
        if raw_estimate <= 2.5 * self.num_registers and zero_registers:
            return self.num_registers * math.log(self.num_registers / zero_registers)

        return raw_estimate

    def memory_bytes(self) -> int:
        return sys.getsizeof(self.registers)

    def _rank(self, suffix: int) -> int:
        remaining_bits = 64 - self.bucket_bits
        if suffix == 0:
            return min(remaining_bits + 1, 255)

        return (suffix & -suffix).bit_length()
