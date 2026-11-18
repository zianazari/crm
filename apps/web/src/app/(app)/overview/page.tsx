import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { OverviewView } from "./overview-view";

export const metadata: Metadata = { title: "نمای کلی" };

export default function OverviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[40rem]" />}>
      <OverviewLoader />
    </Suspense>
  );
}

/** Periods are relative to today in the organization's time zone, so render per request. */
async function OverviewLoader() {
  await connection();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" }).format(new Date());
  return <OverviewView today={today} />;
}
