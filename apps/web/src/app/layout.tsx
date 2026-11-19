import type { Metadata } from "next";
import { Vazirmatn } from "next/font/google";
import { DirectionProvider } from "@base-ui/react/direction-provider";

import { TooltipProvider } from "@/components/ui/tooltip";
import { THEME_SCRIPT } from "@/lib/theme";
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
    // The theme script sets the "dark" class before React hydrates, hence the warning opt-out.
    <html lang="fa" dir="rtl" className={`${vazirmatn.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <DirectionProvider direction="rtl">
          <TooltipProvider>{children}</TooltipProvider>
        </DirectionProvider>
      </body>
    </html>
  );
}
