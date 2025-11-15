package com.caiga;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
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
        this.server.createContext("/state", wrap(exchange -> respondJson(exchange, store.snapshot())));
        this.server.createContext("/inventory", wrap(exchange -> respondJson(exchange, store.inventoryAsMap())));
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
