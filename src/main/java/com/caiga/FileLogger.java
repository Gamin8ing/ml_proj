package com.caiga;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

/**
 * Periodically writes game state snapshots to CSV and JSONL for ML training.
 */
public class FileLogger {
    private static final DateTimeFormatter TS_FMT = DateTimeFormatter.ISO_INSTANT.withZone(ZoneOffset.UTC);

    private final Path csvPath;
    private final Path jsonlPath;
    private final Gson gson = new GsonBuilder().disableHtmlEscaping().create();

    public FileLogger(Path csvPath, Path jsonlPath) {
        this.csvPath = csvPath;
        this.jsonlPath = jsonlPath;
    }

    public synchronized void append(GameStateStore store) {
        GameStateStore.Snapshot s = store.snapshot();
        String timestamp = TS_FMT.format(Instant.now());

        // Compose CSV line
        String movement = s.movementVector == null ? "" : (s.movementVector.dx + "," + s.movementVector.dy + "," + s.movementVector.dz);
        String invJson = gson.toJson(s.inventory);
        String lastEvent = store.getLastEvent() == null ? "" : gson.toJson(store.getLastEvent());

        String csvLine = String.join(",",
                escape(timestamp),
                Double.toString(s.x),
                Double.toString(s.y),
                Double.toString(s.z),
                Float.toString(s.health),
                Integer.toString(s.hunger),
                escape(s.biome),
                escape(s.dimension),
                escape(s.blockUnderCrosshair),
                Boolean.toString(s.isNight),
                escape(movement),
                escape(invJson),
                escape(lastEvent)
        );

        try {
            writeCsvHeaderIfNeeded();
            Files.writeString(csvPath, csvLine + System.lineSeparator(), StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
        } catch (IOException e) {
            CAIGA.LOGGER.warn("Failed writing CSV log: {}", csvPath, e);
        }

        try {
            String json = gson.toJson(new JsonRecord(timestamp, s, store.getLastEvent()));
            Files.writeString(jsonlPath, json + System.lineSeparator(), StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
        } catch (IOException e) {
            CAIGA.LOGGER.warn("Failed writing JSONL log: {}", jsonlPath, e);
        }
    }

    private void writeCsvHeaderIfNeeded() throws IOException {
        if (Files.exists(csvPath) && Files.size(csvPath) > 0) return;
        Files.createDirectories(csvPath.getParent());
        String header = String.join(",",
                "timestamp","x","y","z","health","hunger","biome","dimension",
                "blockUnderCrosshair","isNight","movementVector","inventoryCounts","lastEvent");
        Files.writeString(csvPath, header + System.lineSeparator(), StandardCharsets.UTF_8,
                java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
    }

    private static String escape(String s) {
        if (s == null) return "";
        boolean needsQuotes = s.contains(",") || s.contains("\"") || s.contains("\n");
        if (!needsQuotes) return s;
        return '"' + s.replace("\"", "\"\"") + '"';
    }

    private static class JsonRecord {
        @SuppressWarnings("unused") public final String timestamp;
        @SuppressWarnings("unused") public final GameStateStore.Snapshot state;
        @SuppressWarnings("unused") public final GameStateStore.GameEvent lastEvent;
        JsonRecord(String ts, GameStateStore.Snapshot s, GameStateStore.GameEvent e) {
            this.timestamp = ts;
            this.state = s;
            this.lastEvent = e;
        }
    }
}
