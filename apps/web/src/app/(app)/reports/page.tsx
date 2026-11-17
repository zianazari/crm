import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "گزارش‌ها" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader title="گزارش‌ها" description="گزارش عملکرد فروش و فعالیت‌ها." />
      <ComingSoon summary="گزارش معاملات ورودی، فروش قطعی و دریافتی‌ها." />
    </>
  );
}
