import type { Metadata } from "next";

import { AutomationsView } from "./automations-view";

export const metadata: Metadata = { title: "اتوماسیون" };

export default function AutomationsPage() {
  return <AutomationsView />;
}
