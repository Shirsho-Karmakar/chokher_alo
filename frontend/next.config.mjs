/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  skipTrailingSlashRedirect: true,

  async rewrites() {
    const backend = (process.env.DJANGO_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

    return [
      {
        source: "/backend/:path*/",
        destination: `${backend}/:path*/`
      },
      {
        source: "/backend/:path*",
        destination: `${backend}/:path*`
      }
    ];
  }
};

export default nextConfig;
