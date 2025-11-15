package com.caiga;

import net.fabricmc.api.ModInitializer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

 

public class CAIGA implements ModInitializer {
	public static final String MOD_ID = "caiga";

	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	@Override
	public void onInitialize() {
		LOGGER.info("CAIGA common initialization complete. Client components start in CAIGAClient.");
	}
}