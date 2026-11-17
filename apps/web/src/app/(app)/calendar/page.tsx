import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "تقویم" };

export default function CalendarPage() {
  return (
    <>
      <PageHeader title="تقویم" description="نمای زمانی فعالیت‌ها و جلسه‌ها." />
      <ComingSoon summary="نمای روزانه، هفتگی و ماهانه با تقویم شمسی." />
    </>
  );
}
