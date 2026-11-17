import type { NextConfig } from "next";

// Production only: development tooling needs eval. Next.js injects inline bootstrap
// scripts, hence 'unsafe-inline' for scripts; everything else is same-origin. Photos and
// PDFs are served by the API through this origin, blob: covers previews of camera photos.
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), geolocation=(), microphone=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    const headers = process.env.NODE_ENV === "production" ? [...securityHeaders, { key: "Content-Security-Policy", value: contentSecurityPolicy }] : securityHeaders;
    // API responses (JSON, PDFs) carry the API's own security headers.
    return [{ source: "/((?!api/).*)", headers }];
  },
};

export default nextConfig;
