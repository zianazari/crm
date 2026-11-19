import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { PortalHeader } from "./portal-header";

export const metadata: Metadata = { title: { default: "پنل مشتری", template: "%s | پنل مشتری" }, robots: { index: false } };

/** The customer's own space (spec 4.9): no staff navigation, nothing internal. */
export default function PortalLayout({ children }: LayoutProps<"/portal">) {
  return (
    <Providers>
      <div className="min-h-svh">
        <PortalHeader />
        <main className="mx-auto w-full max-w-3xl space-y-6 p-4 md:p-6">{children}</main>
      </div>
    </Providers>
  );
}
