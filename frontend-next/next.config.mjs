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
    return [
      // The established Django screens remain available under /django while
      // the Next migration is completed privately.
      { source: "/login/", destination: `${djangoOrigin}/login/` },
      { source: "/logout/", destination: `${djangoOrigin}/logout/` },
      // Preserve Django's trailing slash convention. Without it Django sends
      // visitors back to the public route and creates a redirect loop.
      { source: "/django/:path*/", destination: `${djangoOrigin}/:path*/` },
      { source: "/django/:path*", destination: `${djangoOrigin}/:path*/` },
      { source: "/static/:path*", destination: `${djangoOrigin}/static/:path*` },
      { source: "/media/:path*", destination: `${djangoOrigin}/media/:path*` },
    ];
  },
};

export default nextConfig;
