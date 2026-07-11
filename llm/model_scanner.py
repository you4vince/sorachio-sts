"""
Sorachio-STS Model Scanner
Auto-detects GGUF model files and multimodal projectors in model directories.

Scans a given directory for:
  - Main model file (largest .gguf, excluding mmproj)
  - Vision projector (mmproj*.gguf) if present

This allows hot-swapping models by simply dropping new files
into models/llm1/ or models/llm2/ — no config editing required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.logging_setup import get_logger

log = get_logger("llm.model_scanner")


# ---------------------------------------------------------------------------
# ModelInfo — scan result
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    """Result of scanning a model directory."""

    model_path: Path | None = None
    mmproj_path: Path | None = None
    has_vision: bool = False
    model_name: str = "unknown"
    file_size_mb: float = 0.0
    all_gguf_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_model_dir(model_dir: str | Path) -> ModelInfo:
    """
    Scan a directory for GGUF model files.

    Strategy:
      1. List all *.gguf files in the directory
      2. Files containing 'mmproj' in the name → vision projector
      3. Largest remaining .gguf file → main model
      4. Extract human-readable name from filename

    Args:
        model_dir: Path to the model directory (e.g., "models/llm1")

    Returns:
        ModelInfo with detected paths and metadata
    """
    model_dir = Path(model_dir)
    info = ModelInfo()

    if not model_dir.exists():
        log.warning(f"[Scanner] Model directory does not exist: {model_dir}")
        return info

    if not model_dir.is_dir():
        log.warning(f"[Scanner] Path is not a directory: {model_dir}")
        return info

    # Collect all .gguf files
    gguf_files = sorted(model_dir.glob("*.gguf"))
    info.all_gguf_files = [f.name for f in gguf_files]

    if not gguf_files:
        log.warning(f"[Scanner] No .gguf files found in {model_dir}")
        return info

    log.debug(f"[Scanner] Found {len(gguf_files)} GGUF file(s) in {model_dir}")

    # Separate mmproj files from main model files
    mmproj_files: list[Path] = []
    model_files: list[Path] = []

    for f in gguf_files:
        if "mmproj" in f.name.lower():
            mmproj_files.append(f)
        else:
            model_files.append(f)

    # Detect vision projector (pick largest mmproj if multiple)
    if mmproj_files:
        info.mmproj_path = max(mmproj_files, key=lambda f: f.stat().st_size)
        info.has_vision = True
        log.info(
            f"[Scanner] Vision projector detected: {info.mmproj_path.name} "
            f"({info.mmproj_path.stat().st_size / 1024 / 1024:.0f} MB)"
        )

    # Detect main model (pick largest non-mmproj gguf)
    if model_files:
        info.model_path = max(model_files, key=lambda f: f.stat().st_size)
        info.file_size_mb = info.model_path.stat().st_size / 1024 / 1024
        info.model_name = _extract_model_name(info.model_path.name)
        log.info(
            f"[Scanner] Main model detected: {info.model_path.name} "
            f"({info.file_size_mb:.0f} MB) — {info.model_name}"
        )
    else:
        log.warning(f"[Scanner] No main model file found in {model_dir} (only mmproj files)")

    return info


def _extract_model_name(filename: str) -> str:
    """
    Extract a human-readable model name from the GGUF filename.

    Examples:
        "Qwen3.5-0.8B-Q8_0.gguf"     → "Qwen3.5-0.8B"
        "gemma-3-1b-it-Q8_0.gguf"    → "gemma-3-1b-it"
        "Llama-3.2-1B-Q4_K_M.gguf"   → "Llama-3.2-1B"
    """
    name = filename.replace(".gguf", "")

    # Common quantization suffixes to strip
    quant_patterns = [
        "-Q8_0", "-Q6_K", "-Q5_K_M", "-Q5_K_S", "-Q5_1", "-Q5_0",
        "-Q4_K_M", "-Q4_K_S", "-Q4_1", "-Q4_0",
        "-Q3_K_M", "-Q3_K_S", "-Q3_K_L",
        "-Q2_K", "-Q2_K_S",
        "-IQ4_XS", "-IQ4_NL", "-IQ3_XXS", "-IQ3_XS", "-IQ2_XXS",
        "-F16", "-F32", "-BF16",
    ]

    for pattern in quant_patterns:
        if name.upper().endswith(pattern.upper()):
            name = name[: -len(pattern)]
            break

    return name


def log_scan_summary(name: str, info: ModelInfo) -> None:
    """Log a formatted summary of the scan results."""
    if info.model_path:
        log.info(
            f"[{name}] Model: {info.model_name} "
            f"({info.file_size_mb:.0f} MB) "
            f"{'🔮 Vision' if info.has_vision else '📝 Text-only'}"
        )
    else:
        log.warning(f"[{name}] No model detected!")
