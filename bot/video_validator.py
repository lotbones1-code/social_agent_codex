"""Video quality validation to ensure downloads are worth posting."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional


class VideoValidator:
    """Validate video quality before posting."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def validate(self, video_path: Path) -> dict:
        """
        Validate video quality and extract metadata.

        Returns:
            dict with:
                - is_valid: bool
                - file_size_mb: float
                - duration_seconds: float
                - width: int
                - height: int
                - bitrate_kbps: int
                - issues: list of issue descriptions
        """
        issues = []

        # Check file exists
        if not video_path.exists():
            return {
                "is_valid": False,
                "issues": ["Video file does not exist"],
            }

        # Check file size
        file_size = video_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        if file_size < 1024:  # Less than 1KB
            issues.append("File too small (likely corrupted)")

        if file_size_mb > 500:  # X has a limit
            issues.append(f"File too large ({file_size_mb:.1f}MB, X limit is 512MB)")

        # Try to get video metadata with ffprobe
        metadata = self._get_video_metadata(video_path)

        if not metadata:
            issues.append("Cannot read video metadata (may be corrupted)")
            return {
                "is_valid": False,
                "file_size_mb": file_size_mb,
                "issues": issues,
            }

        duration = metadata.get("duration", 0)
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        bitrate = metadata.get("bitrate", 0)

        # Validate duration
        if duration < 0.5:
            issues.append("Video too short (< 0.5 seconds)")
        elif duration > 140:  # X limit is 140 seconds for most accounts
            issues.append(f"Video too long ({duration:.1f}s, X limit is 140s)")

        # Validate resolution
        if width < 320 or height < 240:
            issues.append(f"Resolution too low ({width}x{height})")

        # Validate bitrate (quality check)
        if bitrate > 0 and bitrate < 100:  # 100 kbps is very low
            issues.append(f"Bitrate too low ({bitrate} kbps, may be poor quality)")

        # Check aspect ratio is reasonable
        if width > 0 and height > 0:
            aspect_ratio = width / height
            if aspect_ratio < 0.5 or aspect_ratio > 3:
                issues.append(f"Unusual aspect ratio ({aspect_ratio:.2f})")

        is_valid = len(issues) == 0

        result = {
            "is_valid": is_valid,
            "file_size_mb": file_size_mb,
            "duration_seconds": duration,
            "width": width,
            "height": height,
            "bitrate_kbps": bitrate,
            "issues": issues,
        }

        if is_valid:
            self.logger.info(
                f"✅ Video valid: {width}x{height}, {duration:.1f}s, "
                f"{file_size_mb:.1f}MB, {bitrate}kbps"
            )
        else:
            self.logger.warning(f"❌ Video validation failed: {', '.join(issues)}")

        return result

    def _get_video_metadata(self, video_path: Path) -> Optional[dict]:
        """Extract video metadata using ffprobe."""
        try:
            # Try ffprobe first (more reliable)
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)

                # Extract video stream info
                video_stream = None
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        video_stream = stream
                        break

                if not video_stream:
                    return None

                format_info = data.get("format", {})

                return {
                    "duration": float(format_info.get("duration", 0)),
                    "width": int(video_stream.get("width", 0)),
                    "height": int(video_stream.get("height", 0)),
                    "bitrate": int(format_info.get("bit_rate", 0)) // 1000,  # Convert to kbps
                }

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as exc:
            self.logger.debug(f"ffprobe failed: {exc}")

        # Fallback: basic file checks only
        return {
            "duration": 0,
            "width": 0,
            "height": 0,
            "bitrate": 0,
        }


__all__ = ["VideoValidator"]
