import type { Metadata } from "next";

import { SettingsView } from "./settings-view";

export const metadata: Metadata = { title: "تنظیمات" };

export default function SettingsPage() {
  return <SettingsView />;
}
