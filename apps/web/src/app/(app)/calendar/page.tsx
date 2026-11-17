import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { CalendarView } from "./calendar-view";

export const metadata: Metadata = { title: "تقویم" };

export default function CalendarPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[36rem]" />}>
      <CalendarLoader />
    </Suspense>
  );
}

/** The calendar opens on "today" in the organization's time zone, so it renders per request. */
async function CalendarLoader() {
  await connection();
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tehran",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return <CalendarView today={today} />;
}
