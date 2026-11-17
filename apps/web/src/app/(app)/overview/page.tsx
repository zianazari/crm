import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "نمای کلی" };

export default function OverviewPage() {
  return (
    <>
      <PageHeader title="نمای کلی" description="خلاصه فروش، فعالیت‌های امروز و فروش‌های نیازمند پیگیری." />
      <ComingSoon summary="شاخص‌های فروش این ماه، دریافتی، مانده دریافت‌نشده، فعالیت‌های امروز و معوق پس از آماده‌شدن API نمایش داده می‌شوند." />
    </>
  );
}
