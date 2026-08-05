"""Minimal readers for source-defined TH06 PBG3 archives and ECL volleys.

The formats here are direct transcriptions of ``pbg3/Pbg3Archive.cpp`` and
``EclManager.hpp`` in the authoritative source clone.  Extracted game data is
never written to the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


@dataclass(frozen=True)
class EclTimelineOpcode:
    """One immutable ``EclTimelineInstr`` from an installed stage asset."""

    source: str
    offset: int
    time: int
    arg0: int
    opcode: int
    size: int
    raw: bytes


@dataclass(frozen=True)
class InstalledEclInstruction:
    """One ordinary ECL instruction with a relocation-stable source ID."""

    source: str
    subroutine: int
    offset: int
    relative_offset: int
    time: int
    opcode: int
    size: int
    difficulty_mask: int
    raw: bytes

    @property
    def source_id(self) -> str:
        return f"sub{self.subroutine}+0x{self.relative_offset:x}"

    def executes_on(self, difficulty: int) -> bool:
        if not 0 <= difficulty < 8:
            raise ValueError("ECL difficulty bit must be in 0..7")
        return bool(self.difficulty_mask & (1 << difficulty))


@dataclass(frozen=True)
class EclControlEdge:
    """One audited edge in the installed ECL program graph."""

    source_subroutine: int
    source_relative_offset: int
    kind: str
    target_subroutine: int | None
    target_relative_offset: int | None


@dataclass(frozen=True)
class InstalledEclProgram:
    """Relocation-free installed ECL program and its explicit control graph."""

    source: str
    sha256: str
    subroutine_offsets: tuple[int, ...]
    timeline_offsets: tuple[int, int, int]
    instructions: tuple[InstalledEclInstruction, ...]
    edges: tuple[EclControlEdge, ...]

    def subroutine(self, index: int) -> tuple[InstalledEclInstruction, ...]:
        if not 0 <= index < len(self.subroutine_offsets):
            raise IndexError(index)
        return tuple(
            instruction for instruction in self.instructions
            if instruction.subroutine == index
        )

    def instruction(
        self,
        subroutine: int,
        relative_offset: int,
    ) -> InstalledEclInstruction | None:
        return next(
            (
                instruction for instruction in self.instructions
                if instruction.subroutine == subroutine
                and instruction.relative_offset == relative_offset
            ),
            None,
        )


_JUMP_OPCODES = frozenset((2, 3, *range(29, 35)))
_CALL_OPCODES = frozenset((35, *range(37, 43)))
_SUBROUTINE_REFERENCE_KINDS = {
    95: "spawn",
    108: "death-callback",
    109: "interrupt-handler",
    114: "life-callback",
    116: "timer-callback",
}


def parse_ecl_program(data: bytes, source: str) -> InstalledEclProgram:
    """Decode every installed subroutine and source-relative control edge.

    The layout and argument offsets are transcribed from authoritative
    ``EclManager.hpp`` and match the runtime graph reader in ``native.py``.
    This parser does not execute ECL or claim phase semantics; it makes the
    fixed program available to phase-specific offline tooling.
    """
    if len(data) < 16:
        raise SourceAssetError(f"truncated ECL header in {source}")
    sub_count, _main_count = struct.unpack_from("<hh", data)
    if not 0 <= sub_count <= 4096 or 16 + sub_count * 4 > len(data):
        raise SourceAssetError(f"invalid ECL subroutine table in {source}")
    timeline_offsets = struct.unpack_from("<III", data, 4)
    if any(offset and not 16 <= offset < len(data) for offset in timeline_offsets):
        raise SourceAssetError(f"invalid ECL timeline offset in {source}")
    subroutine_offsets = struct.unpack_from(f"<{sub_count}I", data, 16)
    if any(not 16 <= offset < len(data) for offset in subroutine_offsets):
        raise SourceAssetError(f"invalid ECL subroutine offset in {source}")
    if tuple(sorted(subroutine_offsets)) != subroutine_offsets:
        raise SourceAssetError(f"unsorted ECL subroutine table in {source}")

    instructions: list[InstalledEclInstruction] = []
    by_offset: dict[int, InstalledEclInstruction] = {}
    program_boundaries = tuple(sorted({
        *subroutine_offsets,
        *(offset for offset in timeline_offsets if offset),
        len(data),
    }))
    for subroutine, start in enumerate(subroutine_offsets):
        end = next(
            boundary for boundary in program_boundaries if boundary > start
        )
        offset = start
        seen = set()
        while offset not in seen:
            seen.add(offset)
            if offset + 12 > end:
                raise SourceAssetError(
                    f"truncated sub{subroutine} instruction in {source}"
                )
            time_value, opcode, size = struct.unpack_from("<ihh", data, offset)
            if time_value < 0 or opcode < 0:
                break
            if size < 12 or offset + size > end:
                raise SourceAssetError(
                    f"invalid sub{subroutine} instruction size in {source}"
                )
            instruction = InstalledEclInstruction(
                source=source,
                subroutine=subroutine,
                offset=offset,
                relative_offset=offset - start,
                time=time_value,
                opcode=opcode,
                size=size,
                difficulty_mask=data[offset + 9],
                raw=data[offset:offset + size],
            )
            instructions.append(instruction)
            by_offset[offset] = instruction
            offset += size
        else:
            raise SourceAssetError(f"cyclic linear subroutine in {source}")

    edges: list[EclControlEdge] = []

    def add_edge(
        instruction: InstalledEclInstruction,
        kind: str,
        target_offset: int | None,
        target_subroutine: int | None = None,
    ) -> None:
        target = by_offset.get(target_offset) if target_offset is not None else None
        if target_offset is not None and target is None:
            raise SourceAssetError(
                f"{instruction.source_id} has invalid {kind} target "
                f"0x{target_offset:x} in {source}"
            )
        if target is not None:
            target_subroutine = target.subroutine
            target_relative = target.relative_offset
        else:
            target_relative = None
        edges.append(EclControlEdge(
            instruction.subroutine,
            instruction.relative_offset,
            kind,
            target_subroutine,
            target_relative,
        ))

    for instruction in instructions:
        fallthrough = instruction.offset + instruction.size
        # RET has no statically known target. An unconditional JUMP does not
        # fall through; conditional jumps and JUMPDEC retain both branches.
        if instruction.opcode not in (2, 36) and fallthrough in by_offset:
            add_edge(instruction, "fallthrough", fallthrough)
        if instruction.opcode in _JUMP_OPCODES:
            if len(instruction.raw) < 20:
                raise SourceAssetError(
                    f"short jump at {instruction.source_id} in {source}"
                )
            jump_offset = struct.unpack_from("<i", instruction.raw, 16)[0]
            add_edge(instruction, "jump", instruction.offset + jump_offset)
        if instruction.opcode in _CALL_OPCODES:
            if len(instruction.raw) < 16:
                raise SourceAssetError(
                    f"short call at {instruction.source_id} in {source}"
                )
            sub_id = struct.unpack_from("<i", instruction.raw, 12)[0]
            if not 0 <= sub_id < sub_count:
                raise SourceAssetError(
                    f"invalid call subroutine {sub_id} at "
                    f"{instruction.source_id} in {source}"
                )
            add_edge(
                instruction,
                "call",
                subroutine_offsets[sub_id],
                sub_id,
            )
        reference_kind = _SUBROUTINE_REFERENCE_KINDS.get(instruction.opcode)
        if reference_kind is not None:
            if len(instruction.raw) < 16:
                raise SourceAssetError(
                    f"short {reference_kind} at {instruction.source_id}"
                )
            sub_id = struct.unpack_from("<i", instruction.raw, 12)[0]
            # Callback opcodes use -1 to clear a callback. ENEMYCREATE and
            # interrupt registration require a real installed subroutine.
            if sub_id < 0 and instruction.opcode in (108, 114, 116):
                continue
            if not 0 <= sub_id < sub_count:
                raise SourceAssetError(
                    f"invalid {reference_kind} subroutine {sub_id} at "
                    f"{instruction.source_id} in {source}"
                )
            add_edge(
                instruction,
                reference_kind,
                subroutine_offsets[sub_id],
                sub_id,
            )

    return InstalledEclProgram(
        source=source,
        sha256=hashlib.sha256(data).hexdigest(),
        subroutine_offsets=tuple(subroutine_offsets),
        timeline_offsets=tuple(timeline_offsets),
        instructions=tuple(instructions),
        edges=tuple(edges),
    )


def parse_ecl_timeline(
    data: bytes,
    source: str,
) -> tuple[EclTimelineOpcode, ...]:
    """Decode the source timeline without executing any stage behavior."""
    if len(data) < 16:
        raise SourceAssetError(f"truncated ECL header in {source}")
    timeline_offset = struct.unpack_from("<I", data, 4)[0]
    if not 16 <= timeline_offset <= len(data) - 8:
        raise SourceAssetError(f"invalid ECL timeline offset in {source}")
    result = []
    offset = timeline_offset
    seen = set()
    while offset not in seen:
        seen.add(offset)
        if offset + 4 > len(data):
            raise SourceAssetError(f"truncated timeline instruction in {source}")
        time = struct.unpack_from("<h", data, offset)[0]
        # Shipped ECL timelines end in a four-byte ``(-1, arg0)`` sentinel;
        # it has no opcode/size fields despite the ordinary C++ struct view.
        if time < 0:
            break
        if offset + 8 > len(data):
            raise SourceAssetError(f"truncated timeline instruction in {source}")
        time, arg0, opcode, size = struct.unpack_from("<hhhh", data, offset)
        if size < 8 or offset + size > len(data):
            raise SourceAssetError(f"invalid timeline instruction size in {source}")
        result.append(EclTimelineOpcode(
            source=source,
            offset=offset,
            time=time,
            arg0=arg0,
            opcode=opcode,
            size=size,
            raw=data[offset:offset + size],
        ))
        offset += size
    else:
        raise SourceAssetError(f"cyclic ECL timeline in {source}")
    return tuple(result)


def load_stage_timeline(
    stage_archive: str | Path,
    stage: int,
) -> tuple[EclTimelineOpcode, ...]:
    if not 1 <= stage <= 7:
        raise ValueError("TH06 stage must be in 1..7")
    archive = Pbg3Archive.open(stage_archive)
    source = f"ecldata{stage}.ecl"
    return parse_ecl_timeline(archive.read(source), source)


def load_stage_ecl_program(
    stage_archive: str | Path,
    stage: int,
) -> InstalledEclProgram:
    """Load the complete fixed ECL program for one installed stage."""
    if not 1 <= stage <= 7:
        raise ValueError("TH06 stage must be in 1..7")
    archive = Pbg3Archive.open(stage_archive)
    source = f"ecldata{stage}.ecl"
    return parse_ecl_program(archive.read(source), source)


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
