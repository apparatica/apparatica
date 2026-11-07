// The origin of the site as people open it: `PUBLIC_BASE_URL` of the web server, the same as
// `APX_PUBLIC_BASE_URL` of the API (docs/configuration.md). Absolute addresses of the metadata
// (`og:image`, `og:url`) are built from it, not from the `Host` of a request.
const DEFAULT = "http://localhost:3000";

export const siteUrl = (): URL => new URL(process.env.PUBLIC_BASE_URL || DEFAULT);
