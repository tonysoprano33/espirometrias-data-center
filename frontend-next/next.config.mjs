const djangoOrigin = process.env.DJANGO_ORIGIN || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${djangoOrigin}/api/v1/:path*`,
      },
      // Keep the Django session on the same browser origin during local QA.
      {
        source: "/login/",
        destination: `${djangoOrigin}/login/`,
      },
      {
        source: "/logout/",
        destination: `${djangoOrigin}/logout/`,
      },
      // Temporary bridge to the proven Django screens while Next remains read-only.
      {
        source: "/django/:path*",
        destination: `${djangoOrigin}/:path*`,
      },
      {
        source: "/static/:path*",
        destination: `${djangoOrigin}/static/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${djangoOrigin}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
