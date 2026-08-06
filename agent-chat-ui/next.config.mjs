import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @type {import('next').NextConfig} */
const nextConfig = (phase) => ({
  // 开发服务和生产构建不能共享增量产物，否则 next build 会覆盖 next dev
  // 正在使用的 server chunks，出现 Cannot find module './*.js'。
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
  // The floating Next.js dev indicator occupies the chat canvas in local
  // development and is not part of the product UI.
  devIndicators: false,
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
});

export default nextConfig;
