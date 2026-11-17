import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "فعالیت‌ها" };

export default function ActivitiesPage() {
  return (
    <>
      <PageHeader title="فعالیت‌ها" description="تماس‌ها، جلسه‌ها و پیگیری‌ها در همه پرونده‌ها." />
      <ComingSoon summary="فهرست امروز، معوق، فردا و این هفته با ثبت نتیجه و ساخت پیگیری بعدی." />
    </>
  );
}
