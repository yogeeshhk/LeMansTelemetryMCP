"""Bounded parsing of recorded setup metadata through an explicit allowlist."""
import json
import math


MAX_SETUP_JSON_CHARS = 100_000

# Global/axle controls only. Per-wheel WM_* fields stay excluded because the
# telemetry component-to-wheel mapping has not been verified independently.
SETTING_ALLOWLIST = {
    "VM_BRAKE_BALANCE": ("brakes", "Brake balance"),
    "VM_BRAKE_PRESSURE": ("brakes", "Maximum pedal force"),
    "VM_FRONT_WING": ("aero", "Front wing or splitter"),
    "VM_REAR_WING": ("aero", "Rear wing"),
    "VM_DIFF_PRELOAD": ("differential", "Differential preload"),
    "VM_DIFF_POWER": ("differential", "Differential power"),
    "VM_DIFF_COAST": ("differential", "Differential coast"),
    "VM_FRONT_ANTISWAY": ("suspension", "Front anti-roll bar"),
    "VM_REAR_ANTISWAY": ("suspension", "Rear anti-roll bar"),
    "VM_TRACTIONCONTROLMAP": ("electronics", "Traction control"),
    "VM_TRACTIONCONTROLPOWERCUTMAP": ("electronics", "Traction-control power cut"),
    "VM_TRACTIONCONTROLSLIPANGLEMAP": ("electronics", "Traction-control slip angle"),
    "VM_ANTILOCKBRAKESYSTEMMAP": ("electronics", "Anti-lock braking system map"),
    "VM_STEER_LOCK": ("controls", "Steering lock"),
}


def _short_text(value):
    if not isinstance(value, str) or not 0 < len(value) <= 128 or not value.isprintable():
        return None
    return value


def parse_car_setup(raw):
    """Return validated available allowlisted controls; malformed entries are omitted."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_SETUP_JSON_CHARS:
        return {"status": "unsupported", "settings": [], "omitted": 0,
                "warnings": ["Recorded CarSetup JSON is missing or exceeds the bounded size."]}
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        return {"status": "unsupported", "settings": [], "omitted": 0,
                "warnings": ["Recorded CarSetup JSON is malformed."]}
    if not isinstance(document, dict):
        return {"status": "unsupported", "settings": [], "omitted": 0,
                "warnings": ["Recorded CarSetup JSON must be an object."]}
    rows = []
    omitted = 0
    for setting_id, (category, fallback_label) in SETTING_ALLOWLIST.items():
        item = document.get(setting_id)
        if item is None:
            continue
        if not isinstance(item, dict) or type(item.get("available")) is not bool:
            omitted += 1
            continue
        if not item["available"]:
            omitted += 1
            continue
        value, minimum, maximum = (item.get(name) for name in ("value", "minValue", "maxValue"))
        if not all(type(number) in (int, float) and math.isfinite(number)
                   for number in (value, minimum, maximum)) or not minimum <= value <= maximum:
            omitted += 1
            continue
        producer_key = _short_text(item.get("key"))
        if producer_key != setting_id:
            omitted += 1
            continue
        caption = _short_text(item.get("caption"))
        display_value = _short_text(item.get("stringValue"))
        rows.append({
            "setting_id": setting_id,
            "category": category,
            "label": caption or fallback_label,
            "producer_key": producer_key,
            "raw_value": value,
            "declared_range": {"minimum": minimum, "maximum": maximum},
            "display_value": display_value,
            "direction_semantics": "unverified",
        })
    warnings = []
    if omitted:
        warnings.append("Unavailable or malformed allowlisted settings were omitted.")
    return {"status": "available" if rows else "unsupported", "settings": rows,
            "omitted": omitted, "warnings": warnings}
