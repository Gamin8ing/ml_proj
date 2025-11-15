package com.caiga;

import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.client.MinecraftClient;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.registry.Registries;
import net.minecraft.registry.entry.RegistryEntry;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.hit.HitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import net.minecraft.world.biome.Biome;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * Client tick handler that samples state, detects simple events, and updates the GameStateStore.
 */
public class TickHandler {
    private static final Set<Item> LOGS = new HashSet<>();
    private static final Set<Item> PLANKS = new HashSet<>();
    private static final Set<Item> FOODS = new HashSet<>();

    static {
        // Logs and stems
        LOGS.add(Items.OAK_LOG); LOGS.add(Items.SPRUCE_LOG); LOGS.add(Items.BIRCH_LOG);
        LOGS.add(Items.JUNGLE_LOG); LOGS.add(Items.ACACIA_LOG); LOGS.add(Items.DARK_OAK_LOG);
        LOGS.add(Items.MANGROVE_LOG); LOGS.add(Items.CHERRY_LOG);
        LOGS.add(Items.CRIMSON_STEM); LOGS.add(Items.WARPED_STEM);
        // Planks
        PLANKS.add(Items.OAK_PLANKS); PLANKS.add(Items.SPRUCE_PLANKS); PLANKS.add(Items.BIRCH_PLANKS);
        PLANKS.add(Items.JUNGLE_PLANKS); PLANKS.add(Items.ACACIA_PLANKS); PLANKS.add(Items.DARK_OAK_PLANKS);
        PLANKS.add(Items.MANGROVE_PLANKS); PLANKS.add(Items.CHERRY_PLANKS);
        PLANKS.add(Items.CRIMSON_PLANKS); PLANKS.add(Items.WARPED_PLANKS);
        // Foods
        FOODS.add(Items.BREAD); FOODS.add(Items.APPLE); FOODS.add(Items.CARROT);
        FOODS.add(Items.BAKED_POTATO); FOODS.add(Items.COOKED_BEEF); FOODS.add(Items.COOKED_PORKCHOP);
        FOODS.add(Items.COOKED_CHICKEN); FOODS.add(Items.COOKED_MUTTON); FOODS.add(Items.COOKED_RABBIT);
        FOODS.add(Items.COOKED_COD); FOODS.add(Items.COOKED_SALMON); FOODS.add(Items.GOLDEN_CARROT);
    }

    private final GameStateStore store;
    private final FileLogger logger;

    private double lastX, lastY, lastZ;
    private float lastHealth;
    private long tickCounter = 0L;
    private int lastTotalItems = 0;

    private TickHandler(GameStateStore store, FileLogger logger) {
        this.store = store;
        this.logger = logger;
    }

    public static void register(GameStateStore store, FileLogger logger) {
        TickHandler handler = new TickHandler(store, logger);
        ClientTickEvents.END_CLIENT_TICK.register(handler::onTick);
    }

    private void onTick(MinecraftClient client) {
        tickCounter++;
        if (client == null || client.player == null || client.world == null) {
            return;
        }
        PlayerEntity player = client.player;
        World world = client.world;

        // Position & movement vector
        double x = player.getX();
        double y = player.getY();
        double z = player.getZ();
        double dx = x - lastX;
        double dy = y - lastY;
        double dz = z - lastZ;
        lastX = x; lastY = y; lastZ = z;

        store.updatePosition(x, y, z);
        store.updateMovementVector(dx, dy, dz);

        // Health & hunger
        float health = player.getHealth();
        int hunger = player.getHungerManager().getFoodLevel();
        store.updateHealth(health);
        store.updateHunger(hunger);

        // Damage event
        if (lastHealth > 0 && health < lastHealth) {
            Map<String, Object> details = new HashMap<>();
            details.put("from", lastHealth);
            details.put("to", health);
            store.pushEvent(GameStateStore.GameEvent.of("damage", details));
        }
        lastHealth = health;

        // Biome
        String biomeId = "unknown";
        RegistryEntry<Biome> biomeEntry = world.getBiome(player.getBlockPos());
        if (biomeEntry != null) {
            biomeId = biomeEntry.getKey().map(k -> k.getValue().toString()).orElse("unknown");
        }
        store.updateBiome(biomeId);

        // Dimension
        store.updateDimension(world.getRegistryKey().getValue().toString());

        // Time and night flag
        long timeOfDay = world.getTimeOfDay() % 24000L;
        boolean isNight = timeOfDay >= 13000 && timeOfDay <= 23000;
        store.updateTime(timeOfDay, isNight);

        // Crosshair block
        String blockId = null;
        HitResult hit = client.crosshairTarget;
        if (hit instanceof BlockHitResult bhr && hit.getType() == HitResult.Type.BLOCK) {
            BlockPos pos = bhr.getBlockPos();
            BlockState bs = world.getBlockState(pos);
            Block b = bs.getBlock();
            blockId = Registries.BLOCK.getId(b).toString();
        }
        store.updateBlockUnderCrosshair(blockId);

        // Selected item
        ItemStack held = player.getMainHandStack();
        String itemId = held.isEmpty() ? null : Registries.ITEM.getId(held.getItem()).toString();
        store.updateSelectedItem(itemId);

        // Simple inventory counts
        int logs = 0, planks = 0, foods = 0;
        int totalItems = 0;
        java.util.Map<String, Integer> counts = new java.util.HashMap<>();
        java.util.List<GameStateStore.SlotItem> slots = new java.util.ArrayList<>();
        for (int i = 0; i < player.getInventory().size(); i++) {
            ItemStack stack = player.getInventory().getStack(i);
            if (stack == null || stack.isEmpty()) continue;
            Item item = stack.getItem();
            int c = stack.getCount();
            totalItems += c;
            String id = Registries.ITEM.getId(item).toString();
            counts.put(id, counts.getOrDefault(id, 0) + c);
            slots.add(new GameStateStore.SlotItem(i, id, c));
            if (LOGS.contains(item)) logs += c;
            if (PLANKS.contains(item)) planks += c;
            if (FOODS.contains(item)) foods += c;
        }
        store.updateInventorySummary(logs, planks, foods);
        store.updateInventoryFull(counts, slots);

        // Item pickup heuristic: total items increased
        if (totalItems > lastTotalItems) {
            Map<String, Object> d = new HashMap<>();
            d.put("delta", totalItems - lastTotalItems);
            store.pushEvent(GameStateStore.GameEvent.of("pickup", d));
        }
        lastTotalItems = totalItems;

        // Event detection: mining (left click on block) and place (right click)
        if (client.options.attackKey.isPressed() && hit instanceof BlockHitResult) {
            Map<String, Object> d = new HashMap<>();
            d.put("target", blockId);
            store.pushEvent(GameStateStore.GameEvent.of("mine_attempt", d));
        }
        if (client.options.attackKey.isPressed() && hit != null && hit.getType() == HitResult.Type.ENTITY) {
            Map<String, Object> d = new HashMap<>();
            d.put("target", "entity");
            store.pushEvent(GameStateStore.GameEvent.of("attack_attempt", d));
        }
        if (client.options.useKey.isPressed()) {
            Map<String, Object> d = new HashMap<>();
            d.put("item", itemId);
            store.pushEvent(GameStateStore.GameEvent.of("place_attempt", d));
        }

        // Periodic logging every 20 ticks (~1 second)
        if (logger != null && tickCounter % 20L == 0L) {
            logger.append(store);
        }
    }
}
