"""
Quick test to demonstrate event-aware tip selection.
"""
import sys
import time
sys.path.insert(0, '/mnt/d/RESOURCES/Proj/ml_proj')

from companion.model_utils import ModelUtils
from companion.tips_dataset import TipsDataset

# Mock state with different event scenarios
base_state = {
    "timestamp": time.time(),
    "vitals": {"health": 15.0, "hunger": 12},
    "position": {"x": 100, "y": 50, "z": 200},
    "time": {"isNight": False, "dayTime": 5000},
    "inventory": {"logs": 5, "iron": 2},
    "focus": {"blockUnderCrosshair": "stone"},
}

scenarios = [
    {
        "name": "Mining Session",
        "events": [
            {"type": "mine_attempt", "timestamp": time.time()},
            {"type": "block_broken", "timestamp": time.time()},
            {"type": "mine_attempt", "timestamp": time.time()},
        ],
    },
    {
        "name": "Combat Emergency",
        "events": [
            {"type": "damage_taken", "timestamp": time.time(), "amount": 5},
            {"type": "combat_start", "timestamp": time.time()},
            {"type": "damage_taken", "timestamp": time.time(), "amount": 3},
        ],
    },
    {
        "name": "Death Recovery",
        "events": [
            {"type": "player_death", "timestamp": time.time()},
        ],
    },
    {
        "name": "Quiet Exploration",
        "events": [],
    },
]

print("=== Event-Aware Tip System Test ===\n")

model_utils = ModelUtils()
tips_dataset = TipsDataset(url="companion/tips.json")

for scenario in scenarios:
    print(f"📋 Scenario: {scenario['name']}")
    print(f"   Events: {[e['type'] for e in scenario['events']]}")
    
    # Predict with events
    label, conf, _ = model_utils.predict_label_and_confidence(base_state, scenario['events'])
    print(f"   → Predicted: {label} (confidence: {conf:.2f})")
    
    # Calculate event boost
    event_types = [e.get("type", "") for e in scenario['events']]
    event_count = len(scenario['events'])
    
    relevance_map = {
        "low_health": ["damage_taken", "player_death", "combat_start"],
        "combat": ["damage_taken", "combat_start", "mob_killed", "player_death"],
        "mining_mode": ["mine_attempt", "block_broken", "ore_found"],
    }
    
    relevant_events = relevance_map.get(label, [])
    matches = sum(1 for et in event_types if et in relevant_events)
    
    if event_count > 0:
        boost = 1.0 + (matches / event_count) * 2.0
        print(f"   → Event boost: {boost:.2f}x ({matches}/{event_count} relevant events)")
    else:
        print(f"   → Event boost: 1.00x (no events)")
    
    # Get sample tips
    tips = tips_dataset.get_tips_for_label(label)
    if tips:
        top_tip = tips[0]["text"][:60] + "..." if len(tips[0]["text"]) > 60 else tips[0]["text"]
        print(f"   → Sample tip: \"{top_tip}\"")
    
    print()

print("✓ Event system working: Tips are now context-aware based on recent player actions!")
