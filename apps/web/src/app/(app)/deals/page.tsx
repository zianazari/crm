import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "فروش‌ها" };

export default function DealsPage() {
  return (
    <>
      <PageHeader title="فروش‌ها" description="تابلو و فهرست فروش‌ها." />
      <ComingSoon summary="تابلوی فروش با مراحل مسیر فروش و ستون «نتیجه نهایی»." />
    </>
  );
}
