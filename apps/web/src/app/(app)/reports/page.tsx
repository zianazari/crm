import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ReportsView } from "./reports-view";

export const metadata: Metadata = { title: "گزارش‌ها" };

export default function ReportsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[40rem]" />}>
      <ReportsLoader />
    </Suspense>
  );
}

async function ReportsLoader() {
  await connection();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" }).format(new Date());
  return <ReportsView today={today} />;
}
