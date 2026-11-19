import type { Metadata } from "next";

import { PortalHome } from "./portal-home";

export const metadata: Metadata = { title: "درخواست‌های من" };

export default function PortalPage() {
  return <PortalHome />;
}
