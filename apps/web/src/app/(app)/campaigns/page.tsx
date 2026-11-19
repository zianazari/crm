import type { Metadata } from "next";

import { CampaignsView } from "./campaigns-view";

export const metadata: Metadata = { title: "کمپین‌ها" };

export default function CampaignsPage() {
  return <CampaignsView />;
}
