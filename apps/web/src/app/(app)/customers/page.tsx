import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "مشتریان" };

export default function CustomersPage() {
  return (
    <>
      <PageHeader title="مشتریان" description="اشخاص، سازمان‌ها و سابقه ارتباط." />
      <ComingSoon summary="پرونده مشتری شامل اطلاعات تماس، سازمان‌ها، فروش‌ها و خط زمانی." />
    </>
  );
}
