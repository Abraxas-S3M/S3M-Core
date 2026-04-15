"""KLV encoder/decoder utilities for STANAG 4609 metadata payloads."""

from __future__ import annotations

import struct


class KLVEncoder:
    """Encode and decode MISB-style KLV triplets."""

    KEY_UNIX_TIMESTAMP = 2
    KEY_PLATFORM_HEADING = 5
    KEY_PLATFORM_PITCH = 6
    KEY_PLATFORM_ROLL = 7
    KEY_SENSOR_LATITUDE = 13
    KEY_SENSOR_LONGITUDE = 14
    KEY_SENSOR_ALTITUDE = 15
    KEY_SENSOR_HORIZONTAL_FOV = 22
    KEY_SENSOR_VERTICAL_FOV = 23
    KEY_TARGET_LATITUDE = 40
    KEY_TARGET_LONGITUDE = 41
    KEY_UAS_LOCAL_SET_VERSION = 65

    STANDARD_KEYS = {
        KEY_UNIX_TIMESTAMP: "unix_timestamp_us",
        KEY_PLATFORM_HEADING: "platform_heading_deg",
        KEY_PLATFORM_PITCH: "platform_pitch_deg",
        KEY_PLATFORM_ROLL: "platform_roll_deg",
        KEY_SENSOR_LATITUDE: "sensor_latitude_deg",
        KEY_SENSOR_LONGITUDE: "sensor_longitude_deg",
        KEY_SENSOR_ALTITUDE: "sensor_altitude_hae_m",
        KEY_SENSOR_HORIZONTAL_FOV: "sensor_horizontal_fov_deg",
        KEY_SENSOR_VERTICAL_FOV: "sensor_vertical_fov_deg",
        KEY_TARGET_LATITUDE: "target_latitude_deg",
        KEY_TARGET_LONGITUDE: "target_longitude_deg",
        KEY_UAS_LOCAL_SET_VERSION: "uas_local_set_version",
    }

    def encode_klv(self, key: int, value: bytes) -> bytes:
        """Encode a single KLV triplet as key + BER length + value."""
        if not isinstance(key, int):
            raise TypeError("key must be an integer")
        if key < 0 or key > 255:
            raise ValueError("key must be in range 0..255")
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("value must be bytes-like")

        payload = bytes(value)
        return struct.pack(">B", key) + self._encode_length(len(payload)) + payload

    def decode_klv(self, data: bytes) -> list[tuple[int, bytes]]:
        """Decode sequential KLV triplets from a binary byte stream."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")

        raw = bytes(data)
        offset = 0
        items: list[tuple[int, bytes]] = []
        while offset < len(raw):
            key = raw[offset]
            offset += 1
            length, offset = self._decode_length(raw, offset)
            end = offset + length
            if end > len(raw):
                raise ValueError("invalid KLV payload: declared length exceeds buffer")
            items.append((key, raw[offset:end]))
            offset = end
        return items

    def _encode_length(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("length cannot be negative")
        if length < 0x80:
            return struct.pack(">B", length)

        nbytes = max(1, (length.bit_length() + 7) // 8)
        if nbytes > 8:
            raise ValueError("length is too large for BER encoding")
        return struct.pack(">B", 0x80 | nbytes) + length.to_bytes(nbytes, "big")

    def _decode_length(self, data: bytes, offset: int) -> tuple[int, int]:
        if offset >= len(data):
            raise ValueError("invalid KLV payload: missing length field")

        first = data[offset]
        offset += 1
        if first < 0x80:
            return first, offset

        nbytes = first & 0x7F
        if nbytes == 0:
            raise ValueError("invalid BER length form")
        if offset + nbytes > len(data):
            raise ValueError("invalid KLV payload: truncated BER length")
        length = int.from_bytes(data[offset : offset + nbytes], "big")
        return length, offset + nbytes
