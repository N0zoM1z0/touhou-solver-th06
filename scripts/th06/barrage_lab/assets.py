"""Minimal readers for source-defined TH06 PBG3 archives and ECL volleys.

The formats here are direct transcriptions of ``pbg3/Pbg3Archive.cpp`` and
``EclManager.hpp`` in the authoritative source clone.  Extracted game data is
never written to the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import struct


_ECL_VARIABLE_IDS = frozenset(range(-10025, -10000))
_BULLET_OPCODES = frozenset(range(67, 76))
_CONTROL_FLOW_OPCODES = frozenset((2, 3, *range(29, 43)))


class SourceAssetError(ValueError):
    pass


class _BitReader:
    def __init__(self, data: bytes, offset: int = 0, limit: int | None = None):
        self.data = data
        self.byte = offset
        self.bit = 0x80
        self.limit = len(data) if limit is None else limit
        self.current = 0
        self.checksum = 0

    def read_bit(self) -> int:
        if self.bit == 0x80:
            if self.byte >= self.limit:
                raise SourceAssetError("truncated PBG3 bit stream")
            self.current = self.data[self.byte]
            self.byte += 1
            self.checksum += self.current
        value = int(bool(self.current & self.bit))
        self.bit >>= 1
        if not self.bit:
            self.bit = 0x80
        return value

    def read_int(self, bits: int) -> int:
        value = 0
        for _ in range(bits):
            value = (value << 1) | self.read_bit()
        return value

    def read_varint(self) -> int:
        header = (self.read_bit() << 1) | self.read_bit()
        return self.read_int((8, 16, 24, 32)[header])

    def align(self) -> None:
        while self.bit != 0x80:
            self.read_bit()


@dataclass(frozen=True)
class Pbg3Entry:
    name: str
    checksum: int
    data_offset: int
    uncompressed_size: int


class Pbg3Archive:
    """Read only the small PBG3 surface needed for the offline experiment."""

    def __init__(self, data: bytes):
        self._data = data
        if len(data) < 8 or data[:4] != b"PBG3":
            raise SourceAssetError("not a PBG3 archive")
        reader = _BitReader(data, 4)
        count = reader.read_varint()
        self.file_table_offset = reader.read_varint()
        if not 0 < self.file_table_offset < len(data):
            raise SourceAssetError("invalid PBG3 file-table offset")
        table = _BitReader(data, self.file_table_offset)
        entries = []
        for _ in range(count):
            table.read_varint()  # source entry unk2
            table.read_varint()  # source entry unk1
            checksum = table.read_varint()
            data_offset = table.read_varint()
            uncompressed_size = table.read_varint()
            raw_name = bytearray()
            while True:
                value = table.read_int(8)
                if not value:
                    break
                raw_name.append(value)
                if len(raw_name) >= 256:
                    raise SourceAssetError("unterminated PBG3 entry name")
            try:
                name = raw_name.decode("ascii")
            except UnicodeDecodeError:
                name = raw_name.decode("shift_jis")
            entries.append(Pbg3Entry(
                name, checksum, data_offset, uncompressed_size
            ))
        if any(
            entry.data_offset >= self.file_table_offset
            for entry in entries
        ):
            raise SourceAssetError("invalid PBG3 entry offset")
        self.entries = tuple(entries)

    @classmethod
    def open(cls, path: str | Path) -> "Pbg3Archive":
        return cls(Path(path).read_bytes())

    @staticmethod
    def _decompress(
        raw: bytes, expected_size: int, expected_checksum: int
    ) -> bytes:
        reader = _BitReader(raw)
        dictionary = bytearray(0x2000)
        head = 1
        output = bytearray()
        while True:
            if reader.read_bit():
                value = reader.read_int(8)
                output.append(value)
                dictionary[head] = value
                head = (head + 1) & 0x1FFF
            else:
                match_offset = reader.read_int(13)
                if not match_offset:
                    break
                length = reader.read_int(4) + 3
                for index in range(length):
                    value = dictionary[(match_offset + index) & 0x1FFF]
                    output.append(value)
                    dictionary[head] = value
                    head = (head + 1) & 0x1FFF
            if len(output) > expected_size:
                raise SourceAssetError("PBG3 output exceeds declared size")
        reader.align()
        if reader.checksum != expected_checksum:
            raise SourceAssetError(
                f"PBG3 checksum mismatch: {reader.checksum} != {expected_checksum}"
            )
        if len(output) != expected_size:
            raise SourceAssetError(
                f"PBG3 size mismatch: {len(output)} != {expected_size}"
            )
        return bytes(output)

    def read(self, entry: Pbg3Entry | str) -> bytes:
        if isinstance(entry, str):
            try:
                index = next(
                    index for index, value in enumerate(self.entries)
                    if value.name.lower() == entry.lower()
                )
            except StopIteration as exc:
                raise KeyError(entry) from exc
            entry = self.entries[index]
        else:
            index = self.entries.index(entry)
        end = (
            self.entries[index + 1].data_offset
            if index + 1 < len(self.entries)
            else self.file_table_offset
        )
        if not entry.data_offset < end <= self.file_table_offset:
            raise SourceAssetError(f"invalid compressed range for {entry.name}")
        return self._decompress(
            self._data[entry.data_offset:end],
            entry.uncompressed_size,
            entry.checksum,
        )


@dataclass(frozen=True)
class BulletEffects:
    ints: tuple[int, int, int, int]
    floats: tuple[float, float, float, float]


@dataclass(frozen=True)
class EclBulletOpcode:
    source: str
    subroutine: int
    offset: int
    time: int
    difficulty_mask: int
    opcode: int
    sprite: int
    color: int
    count1: int
    count2: int
    speed1: float
    speed2: float
    angle1: float
    angle2: float
    flags: int
    effects_by_difficulty: tuple[
        BulletEffects | None,
        BulletEffects | None,
        BulletEffects | None,
        BulletEffects | None,
        BulletEffects | None,
    ] = (None, None, None, None, None)

    @property
    def aim_mode(self) -> int:
        return self.opcode - 67

    def executes_on(self, difficulty: int) -> bool:
        return bool(self.difficulty_mask & (1 << difficulty))

    def effects_for(self, difficulty: int) -> BulletEffects | None:
        return self.effects_by_difficulty[difficulty]

    @property
    def has_literal_arguments(self) -> bool:
        values = (self.count1, self.count2)
        floats = (self.speed1, self.speed2, self.angle1, self.angle2)
        return (
            not any(value in _ECL_VARIABLE_IDS for value in values + floats)
            and self.count1 > 0
            and self.count2 > 0
            and self.count1 * self.count2 <= 640
            and all(math.isfinite(value) for value in floats)
            and 0 <= self.sprite < 10
        )


def parse_ecl_bullet_opcodes(data: bytes, source: str) -> tuple[EclBulletOpcode, ...]:
    """Catalogue raw bullet instructions without pretending to execute ECL."""
    if len(data) < 16:
        raise SourceAssetError(f"truncated ECL header in {source}")
    sub_count, _main_count = struct.unpack_from("<hh", data)
    if not 0 <= sub_count <= 4096 or 16 + sub_count * 4 > len(data):
        raise SourceAssetError(f"invalid ECL subroutine table in {source}")
    sub_offsets = struct.unpack_from(f"<{sub_count}I", data, 16)
    result = []
    for subroutine, start in enumerate(sub_offsets):
        if not 0 <= start <= len(data) - 12:
            raise SourceAssetError(f"invalid ECL subroutine offset in {source}")
        offset = start
        seen = set()
        effects_by_difficulty: list[BulletEffects | None] = [None] * 5
        while offset not in seen:
            seen.add(offset)
            if offset + 12 > len(data):
                raise SourceAssetError(f"truncated ECL instruction in {source}")
            time, opcode, size = struct.unpack_from("<ihh", data, offset)
            if time == -1 or opcode == -1:
                break
            if size < 12 or offset + size > len(data):
                raise SourceAssetError(f"invalid ECL instruction size in {source}")
            if opcode in _BULLET_OPCODES:
                if size < 44:
                    raise SourceAssetError(f"short bullet instruction in {source}")
                sprite, color, count1, count2, speed1, speed2, angle1, angle2, flags = struct.unpack_from(
                    "<hhIIffffi", data, offset + 12
                )
                result.append(EclBulletOpcode(
                    source=source,
                    subroutine=subroutine,
                    offset=offset,
                    time=time,
                    difficulty_mask=data[offset + 9],
                    opcode=opcode,
                    sprite=sprite,
                    color=color,
                    count1=struct.unpack("<i", struct.pack("<I", count1))[0],
                    count2=struct.unpack("<i", struct.pack("<I", count2))[0],
                    speed1=speed1,
                    speed2=speed2,
                    angle1=angle1,
                    angle2=angle2,
                    flags=flags,
                    effects_by_difficulty=tuple(effects_by_difficulty),
                ))
            elif opcode == 82:
                if size < 44:
                    raise SourceAssetError(f"short bullet-effects instruction in {source}")
                effect_ints = struct.unpack_from("<iiii", data, offset + 12)
                effect_floats = struct.unpack_from("<ffff", data, offset + 28)
                effects = (
                    None
                    if any(
                        value in _ECL_VARIABLE_IDS
                        for value in effect_ints + effect_floats
                    ) or not all(math.isfinite(value) for value in effect_floats)
                    else BulletEffects(effect_ints, effect_floats)
                )
                difficulty_mask = data[offset + 9]
                for difficulty in range(5):
                    if difficulty_mask & (1 << difficulty):
                        effects_by_difficulty[difficulty] = effects
            if opcode in _CONTROL_FLOW_OPCODES:
                # Effects persist at runtime, but a raw linear scan cannot
                # prove which incoming branch/callee wrote them.
                effects_by_difficulty = [None] * 5
            offset += size
    return tuple(result)


def load_ecl_bullet_catalogue(
    stage_archive: str | Path,
) -> tuple[EclBulletOpcode, ...]:
    archive = Pbg3Archive.open(stage_archive)
    result = []
    for entry in archive.entries:
        if entry.name.lower().endswith(".ecl"):
            result.extend(parse_ecl_bullet_opcodes(
                archive.read(entry), entry.name
            ))
    return tuple(result)
