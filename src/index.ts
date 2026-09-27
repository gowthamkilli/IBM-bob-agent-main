import dotenv from "dotenv";
import { Agent } from "./agent";

dotenv.config();

async function main(): Promise<void> {
  const agent = new Agent({
    apiKey: process.env.IBM_API_KEY ?? "",
    projectId: process.env.IBM_PROJECT_ID ?? "",
    serviceUrl: process.env.IBM_SERVICE_URL ?? "https://us-south.ml.cloud.ibm.com",
    modelId: process.env.MODEL_ID ?? "ibm/granite-13b-instruct-v2",
    logLevel: (process.env.LOG_LEVEL as "debug" | "info" | "warn" | "error") ?? "info",
  });

  await agent.run();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
