import type { Metadata } from "next";
import "./globals.css";
import React from "react";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import AgentSessionKeeper from "@/components/auth/agent-session-keeper";

export const metadata: Metadata = {
  title: "KodAgent",
  description: "KodAgent OA 智能助手",
  icons: {
    icon: "/kodagent-icon.svg",
    shortcut: "/kodagent-icon.svg",
    apple: "/kodagent-icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <NuqsAdapter>
          <AgentSessionKeeper />
          {children}
        </NuqsAdapter>
      </body>
    </html>
  );
}
