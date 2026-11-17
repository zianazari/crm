import type { Metadata } from "next";
import { Vazirmatn } from "next/font/google";
import { DirectionProvider } from "@base-ui/react/direction-provider";

import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

// next/font downloads the font at build time and serves it from our own origin.
const vazirmatn = Vazirmatn({
  variable: "--font-vazirmatn",
  subsets: ["arabic", "latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "CRM",
    template: "%s | CRM",
  },
  description: "مدیریت مشتریان، فروش‌ها و فعالیت‌ها",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fa" dir="rtl" className={`${vazirmatn.variable} h-full antialiased`}>
      <body className="min-h-full">
        <DirectionProvider direction="rtl">
          <TooltipProvider>{children}</TooltipProvider>
        </DirectionProvider>
      </body>
    </html>
  );
}
