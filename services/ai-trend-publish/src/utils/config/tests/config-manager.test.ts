import { assertEquals } from "@std/assert";
import process from "node:process";
import { ConfigManager } from "../config-manager.ts";

Deno.test("ConfigManager defaults database source off when ENABLE_DB is missing", async () => {
  const previous = process.env.ENABLE_DB;
  delete process.env.ENABLE_DB;

  try {
    const manager = ConfigManager.getInstance();
    manager.clearSources();

    await manager.initDefaultConfigSources();

    assertEquals(manager.getSources().length, 1);
  } finally {
    const manager = ConfigManager.getInstance();
    manager.clearSources();
    if (previous === undefined) {
      delete process.env.ENABLE_DB;
    } else {
      process.env.ENABLE_DB = previous;
    }
  }
});
