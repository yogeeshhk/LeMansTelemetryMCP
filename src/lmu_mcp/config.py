"""Fixed personal-project settings; no directory environment or CLI overrides."""
from pathlib import Path

TELEMETRY_ROOT = Path(r"D:\Steam\steamapps\common\Le Mans Ultimate\UserData\Telemetry")
MAX_TABLES = 512
MAX_CATALOG_ROWS = 1024

# Baseline request bounds apply from the first public tool.
MAX_SOURCE_SAMPLES = 2_000_000
MAX_TOTAL_SOURCE_SAMPLES = 10_000_000
MAX_OUTPUT_SAMPLES = 5000
MAX_OUTPUT_VALUES = 20_000
MAX_OUTPUT_BYTES = 300_000
MAX_CHANNELS = 20
MAX_LAPS_PER_REQUEST = 10
MIN_RESOLUTION_M = 0.1
MAX_DISTANCE_RANGE_HIGH_RES_M = 2000
