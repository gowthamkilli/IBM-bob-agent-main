export interface AgentConfig {
  apiKey: string;
  projectId: string;
  serviceUrl: string;
  modelId: string;
  logLevel: "debug" | "info" | "warn" | "error";
}

export class Agent {
  private readonly config: AgentConfig;

  constructor(config: AgentConfig) {
    this.config = config;
  }

  private log(level: AgentConfig["logLevel"], message: string, ...args: unknown[]): void {
    const levels = { debug: 0, info: 1, warn: 2, error: 3 };
    if (levels[level] >= levels[this.config.logLevel]) {
      const timestamp = new Date().toISOString();
      console[level === "debug" ? "log" : level](`[${timestamp}] [${level.toUpperCase()}] ${message}`, ...args);
    }
  }

  async run(): Promise<void> {
    this.log("info", "Agent starting...");
    this.log("info", `Model: ${this.config.modelId}`);
    this.log("info", `Service URL: ${this.config.serviceUrl}`);

    if (!this.config.apiKey) {
      throw new Error("IBM_API_KEY is required. Copy .env.example to .env and set your credentials.");
    }

    // TODO: implement agent loop — tool calls, watsonx inference, etc.
    this.log("info", "Agent ready.");
  }
}
