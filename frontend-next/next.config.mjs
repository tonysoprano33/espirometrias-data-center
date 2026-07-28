/** @type {import('next').NextConfig} */
const nextConfig = {
  trailingSlash: false,
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
