import struct
import unittest

from th06.barrage_lab.assets import (
    Pbg3Archive,
    parse_ecl_bullet_opcodes,
)
from th06.barrage_lab.generator import generate_barrage_case
from th06.barrage_lab.oracle import certify_linear_source
from th06.barrage_lab.runner import python_action_names


class BitWriter:
    def __init__(self):
        self.bits = []

    def bit(self, value):
        self.bits.append(int(bool(value)))

    def integer(self, value, width):
        for shift in range(width - 1, -1, -1):
            self.bit(value & (1 << shift))

    def varint(self, value):
        width = next(width for width in (8, 16, 24, 32) if value < 1 << width)
        header = {8: 0, 16: 1, 24: 2, 32: 3}[width]
        self.integer(header, 2)
        self.integer(value, width)

    def bytes(self):
        while len(self.bits) % 8:
            self.bit(0)
        result = bytearray()
        for start in range(0, len(self.bits), 8):
            value = 0
            for bit in self.bits[start:start + 8]:
                value = (value << 1) | bit
            result.append(value)
        return bytes(result)


def literal_stream(data):
    writer = BitWriter()
    for value in data:
        writer.bit(1)
        writer.integer(value, 8)
    writer.bit(0)
    writer.integer(0, 13)
    return writer.bytes()


def ecl_bytes():
    header = struct.pack("<hhIII", 1, 0, 0, 0, 0) + struct.pack("<I", 20)
    instruction = struct.pack(
        "<ihhBBBBhhiiffffi",
        17, 67, 44, 0, 0x04, 0, 0,
        2, 7, 5, 3, 4.0, 1.0, 0.25, 0.1, 0x04,
    )
    terminal = struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0)
    return header + instruction + terminal


def pbg3_bytes(name, payload):
    compressed = literal_stream(payload)
    data_offset = 7
    table_offset = data_offset + len(compressed)
    header = BitWriter()
    header.varint(1)
    header.varint(table_offset)
    header_bytes = header.bytes()
    assert len(header_bytes) == 3
    table = BitWriter()
    table.varint(0)
    table.varint(0)
    table.varint(sum(compressed))
    table.varint(data_offset)
    table.varint(len(payload))
    for value in name.encode("ascii") + b"\0":
        table.integer(value, 8)
    return b"PBG3" + header_bytes + compressed + table.bytes()


class BarrageLabTests(unittest.TestCase):
    def test_source_archive_and_ecl_catalogue(self):
        archive = Pbg3Archive(pbg3_bytes("test.ecl", ecl_bytes()))
        self.assertEqual([entry.name for entry in archive.entries], ["test.ecl"])
        opcodes = parse_ecl_bullet_opcodes(
            archive.read("test.ecl"), "test.ecl"
        )
        self.assertEqual(len(opcodes), 1)
        opcode = opcodes[0]
        self.assertTrue(opcode.has_literal_arguments)
        self.assertTrue(opcode.executes_on(2))
        self.assertEqual((opcode.aim_mode, opcode.count1, opcode.count2), (0, 5, 3))

    def test_variable_pattern_is_not_claimed_literal(self):
        raw = bytearray(ecl_bytes())
        struct.pack_into("<i", raw, 20 + 16, -10001)
        opcode = parse_ecl_bullet_opcodes(bytes(raw), "vars.ecl")[0]
        self.assertFalse(opcode.has_literal_arguments)

    def test_seeded_source_case_matches_independent_oracle(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        first = generate_barrage_case((opcode,), 19, target_bullets=64)
        second = generate_barrage_case((opcode,), 19, target_bullets=64)
        self.assertEqual(first, second)
        expected = certify_linear_source(first.snapshot, 8).actions
        self.assertEqual(python_action_names(first.snapshot, 8), expected)
        self.assertEqual(len(first.snapshot.bullets), 64)


if __name__ == "__main__":
    unittest.main()
