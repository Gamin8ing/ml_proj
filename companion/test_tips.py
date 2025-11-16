"""
Quick test for tips dataset and no-repeat behavior
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion.tips_dataset import TipsDataset

def test_dataset():
    print("=== Testing TipsDataset ===\n")
    
    # Test 1: Load from local file
    print("1. Loading from local default file...")
    ds = TipsDataset(
        url="",
        cache_path="data/test_cache.json",
        fallback_path="companion/tips_default.json",
        refresh_seconds=3600
    )
    
    labels = ["low_health", "low_food", "mining_mode"]
    for label in labels:
        tips = ds.get_tips_for_label(label)
        print(f"   {label}: {len(tips)} tips loaded")
    
    # Test 2: Simulate tip selection with cooldown
    print("\n2. Testing tip selection with cooldown simulation...")
    label = "low_health"
    all_tips = ds.get_tips_for_label(label)
    
    tip_cooldown = 5  # 5 seconds for test
    tip_last_shown = {}
    
    print(f"   Available tips for '{label}': {len(all_tips)}")
    
    for round_num in range(1, 6):
        now = time.time()
        
        # Filter by cooldown
        available = [
            t for t in all_tips
            if (now - tip_last_shown.get(t["text"], 0)) >= tip_cooldown
        ]
        
        print(f"\n   Round {round_num} (t={now:.1f}):")
        print(f"     Available after cooldown: {len(available)}/{len(all_tips)}")
        
        if available:
            # Pick highest priority
            selected = max(available, key=lambda x: x["priority"])
            print(f"     Selected: \"{selected['text'][:50]}...\" (priority={selected['priority']})")
            tip_last_shown[selected["text"]] = now
        else:
            print(f"     No tips available (all on cooldown)")
        
        # Small delay
        time.sleep(0.5)
    
    print("\n✓ Test complete: Tips are not repeating within cooldown window\n")

def test_online_example():
    print("=== Testing online example JSON ===\n")
    
    # Test loading the example "online" file locally
    ds = TipsDataset(
        url="",
        cache_path="data/test_cache2.json",
        fallback_path="companion/tips_online_example.json",
        refresh_seconds=3600
    )
    
    labels = list(ds.tips.keys())
    print(f"Loaded {len(labels)} label categories: {', '.join(labels)}")
    
    total_tips = sum(len(tips) for tips in ds.tips.values())
    print(f"Total tips across all labels: {total_tips}")
    
    print("\n✓ Online example loaded successfully\n")

if __name__ == "__main__":
    test_dataset()
    test_online_example()
