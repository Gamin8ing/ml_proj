"""
features.py - Deterministic featurization for CAIGA companion.

Converts the mod's /state JSON into a flat dict of numeric/categorical
features suitable for classic ML models (trees, forests). The returned dict
always contains all expected keys in a fixed order.
"""

import math
from typing import Dict, Any, List

# Order must match models/feature_columns.json if a trained model is used.
FEATURE_COLUMNS: List[str] = [
	# Position
	"x", "y", "z", "y_level",
	# Vitals
	"health", "hunger",
	# Time
	"timeOfDay", "isNight",
	# Motion
	"dx", "dy", "dz", "speed",
	# Inventory aggregates
	"logs", "planks", "foods",
	# Focus flags
	"block_is_ore", "block_is_log", "block_is_crop",
	# Recent event flags
	"recent_pickup", "recent_mine_attempt", "recent_damage",
	# Other
	"selectedItemExists",
]


def featurize(state: Dict[str, Any]) -> Dict[str, float]:
	"""Convert game state into flat feature dict (defaults are safe)."""
	f: Dict[str, float] = {}

	pos = state.get("position", {})
	f["x"] = float(pos.get("x", 0.0))
	f["y"] = float(pos.get("y", 64.0))
	f["z"] = float(pos.get("z", 0.0))
	f["y_level"] = f["y"]

	vit = state.get("vitals", {})
	f["health"] = float(vit.get("health", 20.0))
	f["hunger"] = int(vit.get("hunger", 20))

	t = state.get("time", {})
	f["timeOfDay"] = int(t.get("timeOfDay", 0))
	f["isNight"] = 1.0 if t.get("isNight", False) else 0.0

	mv = state.get("motion", {})
	f["dx"] = float(mv.get("dx", 0.0))
	f["dy"] = float(mv.get("dy", 0.0))
	f["dz"] = float(mv.get("dz", 0.0))
	f["speed"] = math.sqrt(f["dx"] ** 2 + f["dy"] ** 2 + f["dz"] ** 2)

	inv = state.get("inventory", {})
	f["logs"] = int(inv.get("logs", 0))
	f["planks"] = int(inv.get("planks", 0))
	f["foods"] = int(inv.get("foods", 0))

	focus = state.get("focus", {})
	blk = str(focus.get("blockUnderCrosshair", "")).lower()
	f["block_is_ore"] = 1.0 if "ore" in blk else 0.0
	f["block_is_log"] = 1.0 if "log" in blk else 0.0
	f["block_is_crop"] = 1.0 if any(w in blk for w in ("crop", "wheat", "carrot", "potato")) else 0.0

	ev = state.get("recentEvents", [])
	types = {e.get("type", "") for e in ev}
	f["recent_pickup"] = 1.0 if "pickup" in types else 0.0
	f["recent_mine_attempt"] = 1.0 if "mine_attempt" in types else 0.0
	f["recent_damage"] = 1.0 if "damage" in types else 0.0

	f["selectedItemExists"] = 1.0 if state.get("selectedItemExists", False) else 0.0

	# Ensure full schema present
	return {k: float(f.get(k, 0.0)) for k in FEATURE_COLUMNS}


def get_feature_columns() -> List[str]:
	return FEATURE_COLUMNS.copy()
