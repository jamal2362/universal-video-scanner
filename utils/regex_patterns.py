# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Compiled regex patterns for better performance
"""
import re

# TMDB ID pattern: {tmdb-12345}
TMDB_ID_PATTERN = re.compile(r'\{tmdb-(\d+)\}', re.IGNORECASE)

# Year pattern: 1900-2099
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')

# Resolution pattern: 480p, 720p, 1080p, 2160p (i or p)
RESOLUTION_PATTERN = re.compile(r'\b(480|720|1080|2160)[pi]\b', re.IGNORECASE)

# Video codec pattern
CODEC_PATTERN = re.compile(r'\b(x264|x265|h264|h265|hevc)\b', re.IGNORECASE)

# Source pattern: BluRay, WEBRip, etc.
SOURCE_PATTERN = re.compile(
    r'\b(BluRay|BRRip|WEBRip|WEB-DL|HDRip|DVDRip)\b',
    re.IGNORECASE)

# HDR format pattern
HDR_PATTERN = re.compile(
    r'\b(DV|HDR10\+?|HLG|SDR|Dolby[\.\s]?Vision)\b',
    re.IGNORECASE)

# Brackets pattern for removing bracketed content
BRACKET_PATTERN = re.compile(r'[\[\(].*?[\]\)]')

# Separator pattern: dots, underscores, dashes
SEPARATOR_PATTERN = re.compile(r'[._\-]')

# Whitespace pattern for cleaning up multiple spaces
WHITESPACE_PATTERN = re.compile(r'\s+')
