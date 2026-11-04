"""Record installed distribution licenses and upstream sources for a local build."""

import argparse
import importlib.metadata
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
parts = ["Third-party dependency inventory for this local Windows build", "",
         "This inventory includes build/test distributions and is not a substitute for each license.",
         "Model weights are downloaded separately by the user and have their own terms.", ""]
for distribution in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
    metadata = distribution.metadata
    parts.extend([f"{metadata.get('Name')}: {distribution.version}",
                  f"License: {metadata.get('License-Expression') or metadata.get('License') or 'See license files / upstream'}",
                  f"Source: {metadata.get('Home-page') or metadata.get('Project-URL') or 'See distribution metadata'}"])
    for file in distribution.files or ():
        if file.name.lower() in {"license", "license.txt", "license.md", "copying", "notice", "notice.txt"}:
            path = distribution.locate_file(file)
            if path.is_file() and path.stat().st_size < 250_000:
                parts.extend([f"--- {file} ---", path.read_text(encoding="utf8", errors="replace")])
    parts.append("")
try:
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    parts.extend(["FFmpeg", ffmpeg.stdout, "Upstream source: https://ffmpeg.org/download.html",
                  "Windows build source / build configuration: https://www.gyan.dev/ffmpeg/builds/",
                  "Redistribution must satisfy the actual binary's LGPL/GPL terms, including corresponding source obligations."])
except (OSError, subprocess.SubprocessError):
    parts.append("FFmpeg not found while generating this inventory.")
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text("\n".join(parts), encoding="utf8")
