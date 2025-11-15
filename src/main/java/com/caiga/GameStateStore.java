package com.caiga;

import com.google.gson.annotations.SerializedName;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Thread-safe central store for game state and recent events.
 */
public class GameStateStore {
    public static final int DEFAULT_EVENT_CAPACITY = 256;

    // Core state
    private double x, y, z;
    private float health;
    private int hunger;
    private String dimension; // namespaced id
    private String biome;     // namespaced id
    private long timeOfDay;   // 0..23999
    private boolean isNight;
    private String blockUnderCrosshair; // namespaced block id or null
    private MovementVector movementVector = new MovementVector(0, 0, 0);
    private String selectedItem; // namespaced item id or null

    private InventorySummary inventorySummary = new InventorySummary(0, 0, 0);
    private InventoryFull inventoryFull = new InventoryFull();

    // Event ring buffer
    private final Deque<GameEvent> recentEvents;
    private final int capacity;

    public GameStateStore() {
        this(DEFAULT_EVENT_CAPACITY);
    }

    public GameStateStore(int capacity) {
        this.capacity = Math.max(32, capacity);
        this.recentEvents = new ArrayDeque<>(this.capacity);
    }

    // Snapshot DTO for JSON responses
    public synchronized Snapshot snapshot() {
        Snapshot s = new Snapshot();
        s.x = x; s.y = y; s.z = z;
        s.health = health;
        s.hunger = hunger;
        s.dimension = dimension;
        s.biome = biome;
        s.timeOfDay = timeOfDay;
        s.isNight = isNight;
        s.blockUnderCrosshair = blockUnderCrosshair;
        s.movementVector = new MovementVector(movementVector.dx, movementVector.dy, movementVector.dz);
        s.selectedItem = selectedItem;
        s.inventory = new InventorySummary(inventorySummary.logs, inventorySummary.planks, inventorySummary.foods);
        s.inventoryFull = inventoryFull.copy();
        s.recentEvents = new ArrayList<>(recentEvents);
        return s;
    }

    /**
     * Create a snapshot but limit the number of recent events included to at most n.
     * Use n=0 to omit events; negative n behaves like 0.
     */
    public synchronized Snapshot snapshotLimited(int n) {
        Snapshot s = snapshot();
        int limit = Math.max(0, n);
        if (limit == 0) {
            s.recentEvents = Collections.emptyList();
        } else {
            List<GameEvent> evs = new ArrayList<>();
            int i = 0;
            for (GameEvent e : recentEvents) {
                evs.add(e);
                if (++i >= limit) break;
            }
            s.recentEvents = evs;
        }
        return s;
    }

    public synchronized Map<String, Object> inventoryAsMap() {
        Map<String, Object> m = new HashMap<>();
        m.put("logs", inventorySummary.logs);
        m.put("planks", inventorySummary.planks);
        m.put("foods", inventorySummary.foods);
        return m;
    }

    public synchronized InventoryFull getInventoryFull() {
        return inventoryFull.copy();
    }

    public synchronized List<GameEvent> getRecentEvents(int n) {
        if (n <= 0) return Collections.emptyList();
        List<GameEvent> out = new ArrayList<>();
        int i = 0;
        for (GameEvent e : recentEvents) {
            out.add(e);
            i++;
            if (i >= n) break;
        }
        return out;
    }

    public synchronized GameEvent getLastEvent() {
        return recentEvents.peekFirst();
    }

    // Update methods (thread-safe)
    public synchronized void updatePosition(double x, double y, double z) {
        this.x = x; this.y = y; this.z = z;
    }
    public synchronized void updateHealth(float health) { this.health = health; }
    public synchronized void updateHunger(int hunger) { this.hunger = hunger; }
    public synchronized void updateDimension(String dim) { this.dimension = dim; }
    public synchronized void updateBiome(String biome) { this.biome = biome; }
    public synchronized void updateTime(long timeOfDay, boolean isNight) {
        this.timeOfDay = timeOfDay; this.isNight = isNight;
    }
    public synchronized void updateBlockUnderCrosshair(String blockId) { this.blockUnderCrosshair = blockId; }
    public synchronized void updateMovementVector(double dx, double dy, double dz) {
        this.movementVector = new MovementVector(dx, dy, dz);
    }
    public synchronized void updateSelectedItem(String itemId) { this.selectedItem = itemId; }
    public synchronized void updateInventorySummary(int logs, int planks, int foods) {
        this.inventorySummary = new InventorySummary(logs, planks, foods);
    }

    public synchronized void updateInventoryFull(Map<String, Integer> counts, List<SlotItem> slots) {
        this.inventoryFull = InventoryFull.from(counts, slots);
    }

    public synchronized void pushEvent(GameEvent event) {
        if (event == null) return;
        recentEvents.addFirst(event);
        while (recentEvents.size() > capacity) recentEvents.removeLast();
    }

    // DTOs
    public static class Snapshot {
        public double x, y, z;
        public float health;
        public int hunger;
        public String dimension;
        public String biome;
        public long timeOfDay;
        public boolean isNight;
        public String blockUnderCrosshair;
        public MovementVector movementVector;
        public String selectedItem;
        public InventorySummary inventory;
        public InventoryFull inventoryFull;
        public List<GameEvent> recentEvents;
    }

    public static class MovementVector {
        public double dx, dy, dz;
        public MovementVector(double dx, double dy, double dz) {
            this.dx = dx; this.dy = dy; this.dz = dz;
        }
    }

    public static class InventorySummary {
        public int logs;
        public int planks;
        public int foods;
        public InventorySummary(int logs, int planks, int foods) {
            this.logs = logs; this.planks = planks; this.foods = foods;
        }
    }

    public static class InventoryFull {
        public Map<String, Integer> counts = new HashMap<>();
        public List<SlotItem> slots = new ArrayList<>();

        public InventoryFull copy() {
            InventoryFull f = new InventoryFull();
            f.counts.putAll(this.counts);
            f.slots.addAll(this.slots); // SlotItem is immutable
            return f;
        }

        public static InventoryFull from(Map<String, Integer> counts, List<SlotItem> slots) {
            InventoryFull f = new InventoryFull();
            if (counts != null) f.counts.putAll(counts);
            if (slots != null) f.slots.addAll(slots);
            return f;
        }
    }

    public static class SlotItem {
        public final int index;
        public final String item;
        public final int count;
        public SlotItem(int index, String item, int count) {
            this.index = index;
            this.item = item;
            this.count = count;
        }
    }

    public static class GameEvent {
        public String type; // mine_attempt, place_attempt, damage, pickup, attack
        public long timestamp; // epoch millis
        @SerializedName("details")
        public Map<String, Object> details;

        public static GameEvent of(String type, Map<String, Object> details) {
            GameEvent e = new GameEvent();
            e.type = type;
            e.timestamp = Instant.now().toEpochMilli();
            e.details = details == null ? Collections.emptyMap() : details;
            return e;
        }
    }
}
