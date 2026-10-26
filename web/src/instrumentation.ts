// Development without the backend (NEXT_PUBLIC_API_MOCKING=enabled, docs/frontend.md): requests
// of the Next.js server to the API get the same mocks as the browser.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled") {
    const { server } = await import("./mocks/server");
    server.listen({ onUnhandledFrame: "bypass" });
  }
}
