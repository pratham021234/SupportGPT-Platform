import type { Metadata } from "next";
import "./globals.css";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { AppHeader } from "@/components/layout/AppHeader";

export const metadata: Metadata = {
  title: "SupportGPT AI — Enterprise Reliability Platform",
  description:
    "AI Support Quality, Verification, Policy-Enforced Human Approvals, and Failure Investigation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen">
        <div className="flex">
          {/* Fixed Sidebar */}
          <AppSidebar />

          {/* Main Workspace Canvas (Offset by sidebar width 64 = 16rem = 256px) */}
          <div className="flex-1 ml-64 flex flex-col min-h-screen">
            <AppHeader />
            <main className="flex-1 p-8 bg-gradient-to-b from-slate-950 to-slate-900/60">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
