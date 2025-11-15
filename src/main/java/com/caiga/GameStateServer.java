package com.caiga;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.io.InputStream;
// Client classes are referenced reflectively to avoid classloading on dedicated server environments
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

/**
 * Lightweight HTTP server exposing GameStateStore via JDK built-in HttpServer.
 */
public class GameStateServer {
    private static GameStateServer INSTANCE;

    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    @SuppressWarnings("unused")
    private final GameStateStore store;
    private final HttpServer server;

    private GameStateServer(int port, GameStateStore store) throws IOException {
        this.store = store;
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
    // Limit events in /state to keep payloads small; use /events for full event queries
    this.server.createContext("/state", wrap(exchange -> respondJson(exchange, store.snapshotLimited(64))));
            this.server.createContext("/inventory", wrap(exchange -> {
                var snap = store.snapshotLimited(0); // exclude events
                var payload = new java.util.LinkedHashMap<String, Object>();
                payload.put("summary", snap.inventory);
                if (snap.inventoryFull != null) {
                    payload.put("counts", snap.inventoryFull.counts);
                    payload.put("slots", snap.inventoryFull.slots);
                }
                respondJson(exchange, payload);
            }));
        this.server.createContext("/events", wrap(exchange -> {
            int n = 20;
            try {
                var query = exchange.getRequestURI().getQuery();
                if (query != null) {
                    for (String kv : query.split("&")) {
                        String[] parts = kv.split("=", 2);
                        if (parts.length == 2 && parts[0].equals("n")) {
                            n = Integer.parseInt(parts[1]);
                        }
                    }
                }
            } catch (Exception ignored) { }
            respondJson(exchange, store.getRecentEvents(n));
        }));
    this.server.createContext("/tip", wrap(this::handleTip));
    this.server.setExecutor(java.util.concurrent.Executors.newCachedThreadPool());
    }

    public static synchronized void startSingleton(int port, GameStateStore store) throws IOException {
        if (INSTANCE != null) return;
        GameStateServer s = new GameStateServer(port, store);
        // Access the store once to satisfy strict linters
        if (s.store == null) throw new IllegalStateException("store not initialized");
        s.server.start(); // non-blocking
        INSTANCE = s;
    }

    private void respondJson(HttpExchange exchange, Object payload) throws IOException {
        byte[] body = gson.toJson(payload).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(body);
        }
    }

    private void handleTip(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            // Method not allowed
            exchange.getResponseHeaders().add("Allow", "POST");
            byte[] body = "{\"error\":\"Use POST\"}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(405, body.length);
            try (OutputStream os = exchange.getResponseBody()) { os.write(body); }
            return;
        }
        String raw = readBody(exchange.getRequestBody());
        String msg = null;
        try {
            var jsonObj = com.google.gson.JsonParser.parseString(raw).getAsJsonObject();
            if (jsonObj.has("message")) msg = jsonObj.get("message").getAsString();
            else if (jsonObj.has("tip")) msg = jsonObj.get("tip").getAsString();
        } catch (Exception ignored) {}

        if (msg == null || msg.isBlank()) {
            respondJson(exchange, java.util.Map.of("error","Missing 'message' or 'tip' field"));
            return;
        }

        // Schedule chat send on client thread if possible
        // Use reflection to avoid compile-time dependency in common source set
        try {
            Class<?> mcClass = Class.forName("net.minecraft.client.MinecraftClient");
            Method getInstance = mcClass.getDeclaredMethod("getInstance");
            Object mc = getInstance.invoke(null);
            if (mc != null) {
                Method execute = mcClass.getMethod("execute", Runnable.class);
                Object player = mcClass.getField("player").get(mc); // public field
                if (player != null) {
                    String finalMsg = msg;
                    execute.invoke(mc, (Runnable) () -> {
                        try {
                            Object curPlayer = mcClass.getField("player").get(mc);
                            if (curPlayer != null) {
                                Class<?> textClass = Class.forName("net.minecraft.text.Text");
                                Method literal = textClass.getMethod("literal", String.class);
                                Object textObj = literal.invoke(null, "[TIP] " + finalMsg);
                                curPlayer.getClass().getMethod("sendMessage", textClass).invoke(curPlayer, textObj);
                            }
                        } catch (Exception ignored) {}
                    });
                }
            }
        } catch (Exception ignored) {}
        respondJson(exchange, java.util.Map.of("status","ok","echo",msg));
    }

    private static String readBody(InputStream is) throws IOException {
        if (is == null) return "";
        byte[] buf = is.readAllBytes();
        return new String(buf, StandardCharsets.UTF_8);
    }

    private static HttpHandler wrap(ThrowingHandler h) {
        return exchange -> {
            try {
                h.handle(exchange);
            } catch (Exception e) {
                String msg = "{\"error\":\"" + e.getClass().getSimpleName() + ": " + e.getMessage() + "\"}";
                byte[] body = msg.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
                exchange.sendResponseHeaders(500, body.length);
                try (OutputStream os = exchange.getResponseBody()) {
                    os.write(body);
                }
            } finally {
                exchange.close();
            }
        };
    }

    @FunctionalInterface
    private interface ThrowingHandler { void handle(HttpExchange exchange) throws Exception; }
}
