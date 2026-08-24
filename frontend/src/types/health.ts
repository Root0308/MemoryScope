export interface HealthResponse {
  status: "ok";
  service: "memoryscope-api";
  version: string;
  database: {
    engine: "sqlite";
    status: "configured";
  };
}
