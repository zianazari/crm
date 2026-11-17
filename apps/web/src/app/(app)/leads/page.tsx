import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "مشتریان احتمالی" };

export default function LeadsPage() {
  return (
    <>
      <PageHeader title="مشتریان احتمالی" description="سرنخ‌ها، منبع جذب و وضعیت پیگیری." />
      <ComingSoon summary="فهرست، جست‌وجو، فیلتر و تبدیل مشتری احتمالی به مشتری." />
    </>
  );
}
