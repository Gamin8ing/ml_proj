"""
companion_server.py - CAIGA companion Flask app

Polls the Fabric mod's /state endpoint, predicts a context label, selects a tip
under cooldown/spoiler policies, optionally paraphrases with Gemini, and posts
the tip back into the game via POST /tip. Exposes debug and feedback endpoints.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from companion.model_utils import ModelUtils
from companion.llm_wrapper import paraphrase_with_context, paraphrase_tip_with_recipe
from companion.rag import RAG
from companion.tips_dataset import TipsDataset


# ---------------- config & logging ----------------

def _load_config():
    # Prefer companion/config.env if present, also load standard .env
    load_dotenv(os.path.join(os.path.dirname(__file__), "config.env"))
    load_dotenv()

    cfg = {
        "POLL_INTERVAL_SECONDS": int(os.getenv("POLL_INTERVAL_SECONDS", "15")),
        "POLL_BACKOFF_BASE": float(os.getenv("POLL_BACKOFF_BASE", "1.5")),
        "CONF_THRESHOLD": float(os.getenv("CONF_THRESHOLD", "0.6")),
        "MAX_SPOILER_LEVEL": int(os.getenv("MAX_SPOILER_LEVEL", "1")),
        "GLOBAL_COOLDOWN_SECONDS": int(os.getenv("GLOBAL_COOLDOWN_SECONDS", "15")),
        "LABEL_COOLDOWN_SECONDS": int(os.getenv("LABEL_COOLDOWN_SECONDS", "30")),
        "TIP_COOLDOWN_SECONDS": int(os.getenv("TIP_COOLDOWN_SECONDS", "180")),
        "STATE_URL": os.getenv("STATE_URL", "http://localhost:8080/state"),
        "POST_TIP_URL": os.getenv("POST_TIP_URL", "http://localhost:8080/tip"),
        "MODEL_PATH": os.getenv("MODEL_PATH", "models/context_model.pkl"),
        "LABEL_ENCODER_PATH": os.getenv("LABEL_ENCODER_PATH", "models/label_encoder.pkl"),
        "FEATURE_COLUMNS_PATH": os.getenv("FEATURE_COLUMNS_PATH", "models/feature_columns.json"),
        "LOGS_DIR": os.getenv("LOGS_DIR", "logs"),
        "DATA_DIR": os.getenv("DATA_DIR", "data"),
        "RAG_ENABLED": os.getenv("RAG_ENABLED", "false").lower() == "true",
        "TIPS_DATASET_URL": os.getenv("TIPS_DATASET_URL", ""),
        "TIPS_REFRESH_SECONDS": int(os.getenv("TIPS_REFRESH_SECONDS", "3600")),
        "COMPANION_PORT": int(os.getenv("COMPANION_PORT", "5000")),
    }
    return cfg
CFG = _load_config()

os.makedirs(CFG["LOGS_DIR"], exist_ok=True)
os.makedirs(CFG["DATA_DIR"], exist_ok=True)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
	handlers=[
		logging.StreamHandler(),
		logging.FileHandler(os.path.join(CFG["LOGS_DIR"], "companion.log")),
	],
)
logger = logging.getLogger("companion")


# ---------------- companion server ----------------

class CompanionServer:
	def __init__(self) -> None:
		self.app = Flask(__name__)

		# ML utils
		self.model_utils = ModelUtils(
			model_path=CFG["MODEL_PATH"],
			label_encoder_path=CFG["LABEL_ENCODER_PATH"],
			feature_columns_path=CFG["FEATURE_COLUMNS_PATH"],
		)

		# Dynamic tips dataset
		self.tips_dataset = TipsDataset(
			url=CFG["TIPS_DATASET_URL"],
			cache_path=os.path.join(CFG["DATA_DIR"], "tips_cache.json"),
			fallback_path=os.path.join(os.path.dirname(__file__), "tips_default.json"),
			refresh_seconds=CFG["TIPS_REFRESH_SECONDS"],
		)

		# Optional RAG instance
		self.rag = RAG() if CFG["RAG_ENABLED"] else None

		# Tip timing state
		self.last_state: Optional[Dict[str, Any]] = None
		self.last_tip: Optional[str] = None
		self.last_tip_timestamp: float = 0.0
		self.label_last_tip: Dict[str, float] = {}
		self.tip_last_shown: Dict[str, float] = {}  # per-tip cooldown tracking
		self.label_tips_posted: Dict[str, int] = {}
		self.label_acceptance: Dict[str, int] = {}

		# Event window tracking
		self.last_poll_time: float = time.time()
		self.recent_events: List[Dict[str, Any]] = []  # events from last poll window

		self.polling = True
		self.poll_thread = None

		self._load_state()
		self._setup_routes()

		signal.signal(signal.SIGINT, self._on_signal)
		signal.signal(signal.SIGTERM, self._on_signal)

	# ---- routes ----
	def _setup_routes(self) -> None:
		@self.app.route("/status", methods=["GET"])
		def status():
			return jsonify({
				"model_loaded": self.model_utils.model_loaded,
				"last_polled": (self.last_state or {}).get("timestamp"),
				"last_tip": self.last_tip,
				"config": {
					"poll_interval": CFG["POLL_INTERVAL_SECONDS"],
					"global_cooldown": CFG["GLOBAL_COOLDOWN_SECONDS"],
					"label_cooldown": CFG["LABEL_COOLDOWN_SECONDS"],
					"conf_threshold": CFG["CONF_THRESHOLD"],
					"max_spoiler_level": CFG["MAX_SPOILER_LEVEL"],
					"rag_enabled": bool(self.rag),
				},
			})

		@self.app.route("/tip", methods=["GET"])
		def get_tip():
			if not self.last_state:
				return jsonify({"error": "no state yet"}), 400
			label, conf, probs = self.model_utils.predict_label_and_confidence(
				self.last_state,
				recent_events=self.recent_events
			)
			tip = self._select_tip(label, conf, events=self.recent_events)
			return jsonify({
				"label": label,
				"confidence": conf,
				"probabilities": probs,
				"tip": tip,
				"recent_events": [e.get("type", "unknown") for e in self.recent_events],
				"would_post": bool(tip and conf >= CFG["CONF_THRESHOLD"] and self._check_cooldowns(label)),
				"timestamp": time.time(),
			})

		@self.app.route("/tip/force", methods=["POST"])
		def force_tip():
			data = request.json or {}
			message = str(data.get("message", "")).strip()
			label = str(data.get("label", "manual")).strip()
			spoiler = int(data.get("spoiler_level", 0))
			force = bool(data.get("force", False))
			if not message:
				return jsonify({"error": "message required"}), 400
			if spoiler > CFG["MAX_SPOILER_LEVEL"] and not force:
				return jsonify({"error": "spoiler too high"}), 400
			if not force and not self._check_cooldowns(label):
				return jsonify({"error": "cooldown active"}), 429
			ok = self._post_tip(message)
			if ok:
				self._after_post(label, message, used_rag=0, state_ref="forced")
				return jsonify({"success": True, "message": message})
			return jsonify({"error": "failed to post"}), 500

		@self.app.route("/feedback", methods=["POST"])
		def feedback():
			data = request.json or {}
			ts = data.get("timestamp")
			label = data.get("label")
			accepted = bool(data.get("accepted", False))
			if ts is None or not label:
				return jsonify({"error": "timestamp and label required"}), 400
			self._append_csv(os.path.join(CFG["LOGS_DIR"], "feedback.csv"), [ts, label, accepted, time.time()], header=["timestamp", "label", "accepted", "feedback_time"]) 
			if accepted:
				self.label_acceptance[label] = self.label_acceptance.get(label, 0) + 1
			self._save_state()
			return jsonify({"success": True})

		@self.app.route("/health", methods=["GET"])
		def health():
			return jsonify({"status": "ok", "time": time.time()})

	# ---- polling ----
	def _polling_loop(self) -> None:
		backoff = CFG["POLL_INTERVAL_SECONDS"]
		max_backoff = 300
		while self.polling:
			try:
				r = requests.get(CFG["STATE_URL"], timeout=5)
				if r.status_code == 200:
					self.last_state = r.json()
					self._extract_recent_events()
					self._process_state()
					backoff = CFG["POLL_INTERVAL_SECONDS"]
				else:
					logger.warning(f"state poll status={r.status_code}")
					backoff = min(backoff * CFG["POLL_BACKOFF_BASE"], max_backoff)
			except Exception as e:
				logger.warning(f"state poll error: {e}")
				backoff = min(backoff * CFG["POLL_BACKOFF_BASE"], max_backoff)
			time.sleep(backoff)

	def _extract_recent_events(self) -> None:
		"""Extract events from the last poll window and update recent_events."""
		if not self.last_state:
			return
		
		now = time.time()
		window_start = self.last_poll_time
		self.last_poll_time = now
		
		# Get events from state
		all_events = self.last_state.get("recentEvents", [])
		
		# Filter to events within the poll window (using event timestamps if available)
		self.recent_events = []
		for event in all_events:
			event_time = event.get("timestamp", 0)
			# If no timestamp, assume it's recent
			if event_time == 0 or event_time >= window_start:
				self.recent_events.append(event)
		
		if self.recent_events:
			event_types = [e.get("type", "unknown") for e in self.recent_events]
			logger.debug(f"Recent events in window: {event_types}")

	def _process_state(self) -> None:
		if not self.last_state:
			return
		
		# Pass recent events to model for context-aware prediction
		label, conf, _ = self.model_utils.predict_label_and_confidence(
			self.last_state, 
			recent_events=self.recent_events
		)
		
		if conf < CFG["CONF_THRESHOLD"]:
			return
		
		# Select tip with event-based scoring
		tip = self._select_tip(label, conf, events=self.recent_events)
		if not tip or not self._check_cooldowns(label):
			return

		# Optional RAG/LLM phrasing when special placeholder present
		used_rag = 0
		if "{recipe}" in tip:
			tip = paraphrase_tip_with_recipe(tip, recipe_query=label, rag_instance=self.rag)
			used_rag = 1

		if self._post_tip(tip):
			self._after_post(label, tip, used_rag=used_rag, state_ref=str(self.last_state.get("timestamp", "unknown")))

	# ---- tip selection & posting ----
	def _select_tip(self, label: str, conf: float, events: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
		# Get all tips for this label from dynamic dataset
		all_tips = self.tips_dataset.get_tips_for_label(label)
		
		# Filter by spoiler level and tip-level cooldown
		now = time.time()
		tip_cooldown = CFG["TIP_COOLDOWN_SECONDS"]
		
		cand = [
			t for t in all_tips
			if t["spoiler_level"] <= CFG["MAX_SPOILER_LEVEL"]
			and (now - self.tip_last_shown.get(t["text"], 0)) >= tip_cooldown
		]
		
		if not cand:
			return None
		
		# Calculate event relevance boost
		event_boost = self._calculate_event_boost(label, events or [])
		
		# Score tips by: confidence * priority * event_boost * time_factor
		last = self.label_last_tip.get(label, 0)
		time_since = max(0.0, now - last)
		# Small dampening factor to prefer fresh labels
		time_factor = 1.0 - min(time_since, 60.0) / 120.0
		
		scored = [
			(conf * c["priority"] * event_boost * (1.0 - 0.5 * time_factor), c["text"]) 
			for c in cand
		]
		scored.sort(key=lambda x: x[0], reverse=True)
		
		return scored[0][1] if scored else None

	def _calculate_event_boost(self, label: str, events: List[Dict[str, Any]]) -> float:
		"""
		Calculate a relevance boost (1.0 - 3.0) based on recent events.
		Higher boost = more relevant tip given what just happened.
		"""
		if not events:
			return 1.0
		
		event_types = [e.get("type", "") for e in events]
		event_count = len(events)
		
		# Event-to-label relevance mapping
		relevance_map = {
			"low_health": ["damage_taken", "player_death", "combat_start"],
			"low_food": ["hunger_depleted", "sprint_fail"],
			"combat": ["damage_taken", "combat_start", "mob_killed", "player_death"],
			"mining_mode": ["mine_attempt", "block_broken", "ore_found"],
			"night_risk": ["time_sunset", "mob_spawn_nearby"],
			"near_resource": ["block_targeted", "ore_spotted"],
			"exploring": ["biome_changed", "structure_found", "coordinates_far"],
			"building": ["block_placed", "crafting_table_used"],
			"enchanting": ["enchant_attempt", "exp_gained"],
			"farming": ["crop_harvested", "animal_bred"],
			"nether": ["dimension_nether", "fire_damage", "piglin_aggro"],
		}
		
		relevant_events = relevance_map.get(label, [])
		matches = sum(1 for et in event_types if et in relevant_events)
		
		if matches == 0:
			return 1.0
		
		# Boost formula: 1.0 + (matches / total_events) * 2.0
		# Max boost = 3.0x when all events are relevant
		boost = 1.0 + (matches / event_count) * 2.0
		logger.debug(f"Event boost for '{label}': {boost:.2f}x ({matches}/{event_count} relevant)")
		return min(boost, 3.0)

	def _check_cooldowns(self, label: str) -> bool:
		now = time.time()
		if now - self.last_tip_timestamp < CFG["GLOBAL_COOLDOWN_SECONDS"]:
			return False
		if now - self.label_last_tip.get(label, 0) < CFG["LABEL_COOLDOWN_SECONDS"]:
			return False
		return True

	def _post_tip(self, message: str) -> bool:
		try:
			r = requests.post(CFG["POST_TIP_URL"], json={"message": message}, timeout=5)
			return r.status_code == 200
		except Exception as e:
			logger.error(f"post tip error: {e}")
			return False

	def _after_post(self, label: str, tip: str, used_rag: int, state_ref: str) -> None:
		now = time.time()
		self.last_tip = tip
		self.last_tip_timestamp = now
		self.label_last_tip[label] = now
		self.tip_last_shown[tip] = now  # Track individual tip usage
		self.label_tips_posted[label] = self.label_tips_posted.get(label, 0) + 1
		self._append_csv(
			os.path.join(CFG["LOGS_DIR"], "decisions.csv"),
			[now, label, 1.0, tip, used_rag, state_ref, json.dumps(self.label_last_tip)],
			header=["timestamp", "label", "confidence", "tip", "used_rag", "state_ref", "cooldowns"],
		)
		self._save_state()

	# ---- persistence & utils ----
	def _append_csv(self, path: str, row: list, header: Optional[list] = None) -> None:
		new = not os.path.exists(path)
		with open(path, "a", newline="") as f:
			w = csv.writer(f)
			if new and header:
				w.writerow(header)
			w.writerow(row)

	def _state_path(self) -> str:
		return os.path.join(CFG["DATA_DIR"], "companion_state.json")

	def _load_state(self) -> None:
		try:
			with open(self._state_path(), "r") as f:
				d = json.load(f)
			self.label_last_tip = d.get("label_last_tip", {})
			self.tip_last_shown = d.get("tip_last_shown", {})
			self.label_acceptance = d.get("label_acceptance", {})
			self.label_tips_posted = d.get("label_tips_posted", {})
		except Exception:
			pass

	def _save_state(self) -> None:
		d = {
			"label_last_tip": self.label_last_tip,
			"tip_last_shown": self.tip_last_shown,
			"label_acceptance": self.label_acceptance,
			"label_tips_posted": self.label_tips_posted,
			"last_save": time.time(),
		}
		try:
			with open(self._state_path(), "w") as f:
				json.dump(d, f, indent=2)
		except Exception as e:
			logger.warning(f"save state failed: {e}")

	def _on_signal(self, *_):
		logger.info("Shutting down companion...")
		self.polling = False
		self._save_state()
		sys.exit(0)

	# ---- run ----
	def run(self) -> None:
		self.poll_thread = threading.Thread(target=self._polling_loop, daemon=True)
		self.poll_thread.start()
		self.app.run(host="0.0.0.0", port=CFG["COMPANION_PORT"], debug=False, use_reloader=False)


if __name__ == "__main__":
	server = CompanionServer()
	logger.info("Starting CAIGA companion...")
	server.run()
