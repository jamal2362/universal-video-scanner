# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Media utility functions for parsing and formatting media information
"""
import re


def get_channel_format(channels):
    """Convert channel count to standard format string"""
    try:
        channels = int(channels)
        channel_map = {
            1: "1.0",
            2: "2.0",
            3: "2.1",
            4: "3.1",
            5: "4.1",
            6: "5.1",
            7: "6.1",
            8: "7.1",
            9: "8.1",
            10: "9.1"
        }
        return channel_map.get(channels, f"{channels}.0")
    except (ValueError, TypeError):
        return ""


def parse_mediainfo_int(value):
    """
    Parse a MediaInfo numeric field into an int.

    Handles plain numbers ("3840"), float strings ("7440.192"),
    and multi-value fields like "8 / 6" (first parsable value wins).

    Returns:
        int, or None if nothing parsable
    """
    if value is None:
        return None
    for part in str(value).split('/'):
        try:
            return int(float(part.strip()))
        except ValueError:
            continue
    return None


def parse_mediainfo_float(value):
    """
    Parse a MediaInfo numeric field into a float.

    Handles plain numbers ("7440.192") and multi-value fields
    like "7440.192 / 7440.000" (first parsable value wins).

    Returns:
        float, or None if nothing parsable
    """
    if value is None:
        return None
    for part in str(value).split('/'):
        try:
            return float(part.strip())
        except ValueError:
            continue
    return None


def parse_bitrate_string(bitrate_str):
    """
    Parse bitrate string from MediaInfo and convert to kbit/s.

    Handles formats like:
    - "55.3 Mb/s" -> 55300 kbit/s
    - "9 039 kb/s" -> 9039 kbit/s
    - "1.5 Gb/s" -> 1500000 kbit/s

    Args:
        bitrate_str: String representation of bitrate (e.g., "55.3 Mb/s")

    Returns:
        int: Bitrate in kbit/s, or None if parsing fails
    """
    if not bitrate_str:
        return None

    try:
        # Remove spaces from numbers like "9 039" -> "9039"
        bitrate_str_clean = bitrate_str.replace(' ', '')

        # Match patterns like "55.3Mb/s", "9039kb/s", etc.
        match = re.search(r'([\d.]+)(Mb|Gb|Kb|b)/s', bitrate_str_clean, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()

            # Convert to kbit/s
            if unit == 'gb':
                return int(value * 1000000)
            elif unit == 'mb':
                return int(value * 1000)
            elif unit == 'kb':
                return int(value)
            elif unit == 'b':
                return int(value / 1000)
    except (ValueError, AttributeError):
        pass

    return None
