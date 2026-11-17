import type { Metadata } from "next";

import { ActivitiesView } from "./activities-view";

export const metadata: Metadata = { title: "فعالیت‌ها" };

export default function ActivitiesPage() {
  return <ActivitiesView />;
}
