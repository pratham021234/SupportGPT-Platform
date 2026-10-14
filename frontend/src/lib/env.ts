/**
 * Validated frontend runtime configuration.
 */

export const env = {
  apiUrl: process.env["NEXT_PUBLIC_API_URL"] || "http://localhost:8000",
  appEnv: process.env["NEXT_PUBLIC_APP_ENV"] || "development",
  isProduction: process.env["NODE_ENV"] === "production",
};
