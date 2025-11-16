# Event-Aware Tip System

## Overview

The companion now analyzes **recent events from the last polling window** (default: 15 seconds) to provide contextually relevant tips based on what just happened in the game.

## How It Works

### 1. Event Window Tracking
Every time the companion polls `/state`, it:
- Extracts events from `recentEvents` that occurred since the last poll
- Filters events by timestamp (if available) to ensure they're within the polling window
- Stores them in `self.recent_events` for analysis

### 2. Event-Based Label Prediction
When predicting the player context, the system now considers recent events:

```python
label, conf, _ = model_utils.predict_label_and_confidence(
    state, 
    recent_events=recent_events
)
```

**Priority Overrides** (in fallback rules):
- `player_death` → Immediate "low_health" warning (98% confidence)
- `damage_taken` + low health → "low_health" (95%)
- `combat_start` or `mob_killed` → "combat" (90%)
- `mine_attempt` or `block_broken` → "mining_mode" boost

### 3. Event Relevance Scoring
Each tip is scored with an **event boost** (1.0x - 3.0x) based on how relevant recent events are to that tip's label:

**Relevance Map**:
```python
{
    "low_health": ["damage_taken", "player_death", "combat_start"],
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
```

**Boost Formula**:
```
boost = 1.0 + (relevant_events / total_events) * 2.0
```

Examples:
- **3 mining events** → Mining tip gets **3.0x boost** (100% relevant)
- **2 combat, 1 mining** → Combat tip gets **2.33x boost** (67% relevant)
- **No events** → All tips get **1.0x** (normal priority)

### 4. Final Tip Score
```
score = confidence × priority × event_boost × time_factor
```

Where:
- `confidence`: Model/rule confidence (0.0-1.0)
- `priority`: Tip priority from dataset (1-10)
- `event_boost`: Event relevance multiplier (1.0-3.0)
- `time_factor`: Small dampener for recently used labels (0.5-1.0)

## Examples

### Scenario 1: Mining Session
```
Events: [mine_attempt, block_broken, mine_attempt]
State: Y=35, underground

→ Predicted: mining_mode (75% conf)
→ Event boost: 3.0x (3/3 relevant)
→ Selected tip: "Don't dig straight down—you might fall in lava!"
```

### Scenario 2: Combat Emergency
```
Events: [damage_taken, combat_start, damage_taken]
State: Health=8, night=true

→ Predicted: combat (90% conf)
→ Event boost: 3.0x (3/3 relevant)
→ Selected tip: "Block with a shield to reduce damage!"
```

### Scenario 3: Death Recovery
```
Events: [player_death]
State: Health=20 (respawned)

→ Predicted: low_health (98% conf, override)
→ Event boost: 3.0x (1/1 relevant)
→ Selected tip: "Your health is low—eat food or find shelter."
```

### Scenario 4: Quiet Exploration
```
Events: []
State: Y=70, full health

→ Predicted: exploring (60% conf)
→ Event boost: 1.0x (no events)
→ Selected tip: "Press F3 to see your coordinates."
```

## Benefits

✅ **Context-Aware**: Tips match what the player is currently doing
✅ **Emergency Response**: Critical events (death, combat) trigger urgent tips immediately
✅ **No False Alarms**: Tips only appear when events justify them
✅ **Smart Prioritization**: Multiple events compound to boost highly relevant tips

## API Response Example

`GET /tip` now includes recent events:

```json
{
  "label": "combat",
  "confidence": 0.90,
  "probabilities": {...},
  "tip": "Block with a shield to reduce damage—especially from creeper explosions.",
  "recent_events": ["damage_taken", "combat_start"],
  "would_post": true,
  "timestamp": 1731700000.0
}
```

## Configuration

No new config needed—the system automatically analyzes events from the existing polling interval:

```env
POLL_INTERVAL_SECONDS=15  # Events are tracked within this window
```

## Testing

Run the test script to see event-based selection in action:

```bash
python companion/test_event_system.py
```

Output:
```
📋 Scenario: Combat Emergency
   Events: ['damage_taken', 'combat_start', 'damage_taken']
   → Predicted: combat (confidence: 0.90)
   → Event boost: 3.00x (3/3 relevant events)
   → Sample tip: "Keep your distance and use a bow against tough enemies."
```

## Event Type Reference

**Supported Event Types** (add more in your mod):
- `damage_taken` - Player took damage
- `player_death` - Player died
- `combat_start` - Combat initiated
- `mob_killed` - Killed a mob
- `mine_attempt` - Tried to break a block
- `block_broken` - Successfully broke a block
- `block_placed` - Placed a block
- `ore_found` - Discovered ore
- `time_sunset` - Day → Night transition
- `biome_changed` - Entered new biome
- `structure_found` - Discovered structure
- `crafting_table_used` - Crafted item
- `enchant_attempt` - Used enchanting table
- `crop_harvested` - Harvested crops
- `animal_bred` - Bred animals
- `dimension_nether` - Entered Nether
- `fire_damage` - Took fire damage
- `piglin_aggro` - Angered Piglin

## Adding Custom Events

1. **In your Fabric mod**, add events to the state JSON:
   ```json
   {
     "recentEvents": [
       {
         "type": "custom_event",
         "timestamp": 1731700000,
         "data": {...}
       }
     ]
   }
   ```

2. **In `companion_server.py`**, update the relevance map:
   ```python
   relevance_map = {
       "your_label": ["custom_event", "other_event"],
       ...
   }
   ```

3. **In `model_utils.py`** (optional), add rule overrides:
   ```python
   custom_event_active = "custom_event" in event_types
   if custom_event_active:
       label, conf = "your_label", 0.95
   ```

## Performance

- **Minimal overhead**: Event parsing happens once per poll (~15s)
- **No extra API calls**: Uses existing `recentEvents` from `/state`
- **Smart caching**: Events are only re-extracted when state changes

---

**Result**: The companion now provides **intelligent, action-driven tips** that respond dynamically to what you're doing in the game! 🎮
