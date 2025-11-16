"""
model_utils.py - Model loading and rule-based fallback for CAIGA.

Attempts to load a scikit-learn classifier and label encoder. If unavailable or
prediction fails, uses deterministic rules based on state to pick a context.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional ML imports (lazy)
try:
	import joblib  # type: ignore
	import numpy as np  # type: ignore
	_ML_AVAILABLE = True
except Exception:
	_ML_AVAILABLE = False


class ModelUtils:
	def __init__(
		self,
		model_path: str = "models/context_model.pkl",
		label_encoder_path: str = "models/label_encoder.pkl",
		feature_columns_path: str = "models/feature_columns.json",
	) -> None:
		self.model = None
		self.label_encoder = None
		self.feature_columns = None
		self.model_loaded = False

		if not _ML_AVAILABLE:
			logger.info("ML stack not available; using rule-based predictions.")
			return

		try:
			if os.path.exists(model_path):
				self.model = joblib.load(model_path)
			if os.path.exists(label_encoder_path):
				self.label_encoder = joblib.load(label_encoder_path)
			if os.path.exists(feature_columns_path):
				with open(feature_columns_path, "r") as f:
					self.feature_columns = json.load(f)
			self.model_loaded = all([self.model is not None, self.label_encoder is not None, self.feature_columns is not None])
			if self.model_loaded:
				logger.info("Loaded trained model and metadata.")
			else:
				logger.warning("Model artifacts incomplete; falling back to rules.")
		except Exception as e:
			logger.warning(f"Failed to load model: {e}; using rules.")
			self.model_loaded = False

	def predict_label_and_confidence(
		self, 
		state: Dict[str, Any],
		recent_events: Optional[List[Dict[str, Any]]] = None
	) -> Tuple[str, float, Dict[str, float]]:
		if self.model_loaded and _ML_AVAILABLE:
			try:
				from companion.features import featurize
				feats = featurize(state)
				vec = [feats.get(k, 0.0) for k in self.feature_columns]
				probs = self.model.predict_proba([vec])[0]
				idx = int(np.argmax(probs))
				label = self.label_encoder.inverse_transform([idx])[0]
				conf = float(probs[idx])
				dist = {self.label_encoder.inverse_transform([i])[0]: float(p) for i, p in enumerate(probs)}
				return label, conf, dist
			except Exception as e:
				logger.warning(f"Model prediction failed: {e}; using rules.")
		return self._rules(state, recent_events or [])

	# ------------------ rules fallback ------------------
	def _rules(self, state: Dict[str, Any], events: List[Dict[str, Any]]) -> Tuple[str, float, Dict[str, float]]:
		vit = state.get("vitals", {})
		health = float(vit.get("health", 20.0))
		hunger = int(vit.get("hunger", 20))

		t = state.get("time", {})
		is_night = bool(t.get("isNight", False))

		inv = state.get("inventory", {})
		logs = int(inv.get("logs", 0))

		pos = state.get("position", {})
		y = float(pos.get("y", 64.0))

		# Parse recent events for context
		event_types = {e.get("type", "") for e in events}
		mine_attempt = "mine_attempt" in event_types or "block_broken" in event_types
		took_damage = "damage_taken" in event_types
		combat_active = "combat_start" in event_types or "mob_killed" in event_types
		died_recently = "player_death" in event_types
		
		focus = state.get("focus", {})
		blk = str(focus.get("blockUnderCrosshair", "")).lower()
		near_resource = any(w in blk for w in ("ore", "log", "crop"))

		# Event-driven priority overrides
		if died_recently:
			label, conf = "low_health", 0.98
		elif took_damage and health < 10:
			label, conf = "low_health", 0.95
		elif combat_active:
			label, conf = "combat", 0.90
		elif health < 8:
			label, conf = "low_health", 0.95
		elif hunger < 6:
			label, conf = "low_food", 0.90
		elif is_night and logs < 2:
			label, conf = "night_risk", 0.85
		elif mine_attempt or y <= 32:
			label, conf = "mining_mode", 0.75
		elif near_resource:
			label, conf = "near_resource", 0.70
		else:
			label, conf = "exploring", 0.60

		labels = ["low_health", "low_food", "night_risk", "mining_mode", "near_resource", "exploring", "combat", "building"]
		dist = {l: 0.0 for l in labels}
		dist[label] = conf
		rem = (1.0 - conf) / (len(labels) - 1)
		for l in labels:
			if l != label:
				dist[l] = rem
		return label, conf, dist
