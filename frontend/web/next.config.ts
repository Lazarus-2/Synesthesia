import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // Catch-all: apply baseline security headers to every route.
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          // Content-Security-Policy is intentionally NOT enabled here to avoid
          // breaking the SPA (Google Fonts, Spotify embeds, blob audio, SSE).
          // A recommended starting policy, once validated against the live app:
          //
          //   default-src 'self';
          //   style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
          //   font-src 'self' https://fonts.gstatic.com;
          //   frame-src https://open.spotify.com;
          //   img-src 'self' data: https:;
          //   media-src 'self' blob: <API origin>;
          //   connect-src 'self' <API origin>;   // fetch + SSE
          //
          // Replace <API origin> with the backend base URL and enable only
          // after confirming no console CSP violations in the running app.
          // { key: "Content-Security-Policy", value: "..." },
        ],
      },
    ];
  },
};

export default nextConfig;
