# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Media utility functions for parsing and formatting media information
"""


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
