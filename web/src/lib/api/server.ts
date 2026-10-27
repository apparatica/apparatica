// The API as the Next.js server sees it (docs/api.md): `API_URL` inside the deployment, the API
// process on this machine in development. In the mock mode the mocks of the server answer.
import { createApiClient } from "./client";

export const serverApi = createApiClient({
  baseUrl: process.env.API_URL ?? "http://localhost:8000",
});
