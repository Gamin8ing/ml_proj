package com.caiga;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.loader.api.FabricLoader;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CAIGAClient implements ClientModInitializer {
	private static final Logger LOGGER = LoggerFactory.getLogger(CAIGA.MOD_ID + ":client");

	@Override
	public void onInitializeClient() {
		// Initialize shared store and logging
		GameStateStore store = new GameStateStore();

		Path configDir = FabricLoader.getInstance().getConfigDir().resolve(CAIGA.MOD_ID);
		try {
			Files.createDirectories(configDir);
		} catch (IOException e) {
			LOGGER.warn("Failed to create config directory: {}", configDir, e);
		}

		FileLogger fileLogger = new FileLogger(configDir.resolve("state.csv"), configDir.resolve("state.jsonl"));

		// Register tick handler
		TickHandler.register(store, fileLogger);

		// Start REST server
		try {
			GameStateServer.startSingleton(8080, store);
			LOGGER.info("GameStateServer listening on http://localhost:8080/state");
		} catch (Exception e) {
			LOGGER.error("Failed to start GameStateServer", e);
		}
	}
}