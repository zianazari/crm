import type { Metadata } from "next";

import { AvailabilityView } from "./availability-view";

export const metadata: Metadata = { title: "زمان‌های رزرو" };

export default function AvailabilityPage() {
  return <AvailabilityView />;
}
