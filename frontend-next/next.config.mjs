const djangoOrigin = process.env.DJANGO_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Django's URL configuration uses trailing slashes. Keep them in Next too so
  // API rewrites do not bounce forever between Next (no slash) and Django.
  trailingSlash: true,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    // Clinical work stays on the proven Django interface until each Next
    // screen is functionally equivalent. Applying this before filesystem
    // routing keeps every legacy link, report, PDF and session on the same
    // public domain instead of mixing two incompatible UIs.
    return {
      beforeFiles: [
        {
          source: "/:path*",
          destination: `${djangoOrigin}/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
