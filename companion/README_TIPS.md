# Tips Dataset Guide

## Overview
The companion uses a dynamic tips dataset loaded from `tips.json`. This file can be:
- **Local**: `companion/tips.json` (default, no internet required)
- **Online**: Any HTTP/HTTPS URL pointing to a JSON file

## JSON Structure

```json
{
  "version": "1.0.0",
  "last_updated": "2025-11-16",
  "labels": {
    "label_name": [
      {
        "text": "Tip message shown in-game",
        "spoiler_level": 0,
        "priority": 10
      }
    ]
  }
}
```

### Fields
- **version**: Dataset version (for future compatibility)
- **last_updated**: ISO date of last update
- **labels**: Map of context labels to tip arrays
  - **text**: The tip message (max ~150 chars for chat readability)
  - **spoiler_level**: 0=basic, 1=helpful, 2=detailed (filtered by `MAX_SPOILER_LEVEL`)
  - **priority**: Higher = more likely to be shown (1-10 scale)

## Hosting Your Tips Online

### Option 1: GitHub (Free, Easy)
1. Create a new repo: `minecraft-caiga-tips`
2. Add `tips.json` to the repo
3. Commit and push
4. Get the raw URL: `https://raw.githubusercontent.com/YOUR_USERNAME/minecraft-caiga-tips/main/tips.json`
5. Update `config.env`:
   ```env
   TIPS_DATASET_URL=https://raw.githubusercontent.com/YOUR_USERNAME/minecraft-caiga-tips/main/tips.json
   ```

### Option 2: Gist (Quick Single File)
1. Go to https://gist.github.com/
2. Create a new gist with your `tips.json`
3. Click "Raw" and copy the URL
4. Update `config.env` with the raw URL

### Option 3: Your Own Server
Host `tips.json` on any web server and set:
```env
TIPS_DATASET_URL=https://your-domain.com/caiga/tips.json
```

## How It Works

1. **On Startup**: The companion loads tips from `TIPS_DATASET_URL`
   - If it's a URL, it downloads and caches locally in `data/tips_cache.json`
   - If download fails, it uses the cached version
   - If no cache exists, it falls back to `companion/tips.json`

2. **Periodic Refresh**: Every `TIPS_REFRESH_SECONDS` (default: 1 hour), it re-fetches from the URL

3. **Anti-Repeat Logic**: Each tip tracks when it was last shown
   - Tips won't repeat within `TIP_COOLDOWN_SECONDS` (default: 300s = 5 min)
   - Label cooldown (`LABEL_COOLDOWN_SECONDS`) applies on top
   - If all tips are on cooldown, no tip is shown

## Adding New Labels

To support a new context label (e.g., "flying", "underwater"):

1. Add tips to your `tips.json`:
```json
"flying": [
  {
    "text": "Elytra requires firework rockets to boost speed.",
    "spoiler_level": 2,
    "priority": 8
  }
]
```

2. Update your model training to predict the new label, or add a rule in `model_utils.py`

3. Restart the companion—new tips are loaded automatically

## Current Labels in Default Dataset

- `low_health`: Healing and survival tips
- `low_food`: Food sources and hunger management
- `night_risk`: Night safety and mob avoidance
- `mining_mode`: Underground mining guidance
- `near_resource`: Resource gathering tips
- `exploring`: Navigation and exploration
- `combat`: Fighting strategies
- `building`: Construction advice
- `enchanting`: Enchanting table usage
- `farming`: Agriculture tips
- `nether`: Nether survival
- `redstone`: Redstone mechanics

Total: **~120 unique tips** across 12 categories

## Tips Best Practices

### Writing Good Tips
- **Keep it short**: 1-2 sentences max (~150 chars)
- **Be actionable**: Tell players what to do, not just info
- **Match spoiler level**: 0=obvious, 1=helpful, 2=advanced secrets
- **Set priority wisely**: Critical survival tips = 9-10, nice-to-know = 4-6

### Priority Guidelines
- **10**: Critical survival (low health warning)
- **8-9**: Important gameplay advice (bed usage, food sources)
- **6-7**: Helpful optimization tips
- **4-5**: Advanced techniques and trivia
- **1-3**: Fun facts or rarely applicable tips

### Spoiler Level Guidelines
- **0**: Everyone knows this (e.g., "eat food to restore health")
- **1**: Most players learn quickly (e.g., "cooked food is better")
- **2**: Advanced mechanics or locations (e.g., "diamond Y-level -59")

## Testing Your Tips

```bash
# Test tip loading and cooldown logic
python companion/test_tips.py

# Force a specific tip in-game
curl -X POST http://localhost:5000/tip/force \
  -H 'Content-Type: application/json' \
  -d '{"message":"Your custom tip here","label":"test","force":true}'
```

## Updating Tips Live

If using an online URL:
1. Edit your hosted `tips.json`
2. Wait up to `TIPS_REFRESH_SECONDS` (or restart companion)
3. New tips are loaded automatically

No code changes needed—just edit the JSON!
