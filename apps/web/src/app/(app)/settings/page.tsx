import type { Metadata } from "next";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "تنظیمات" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="تنظیمات" description="کاربران، تیم‌ها، مراحل فروش و منابع جذب." />
      <ComingSoon summary="مدیریت کاربران، تیم‌ها، مسیر فروش و منابع." />
    </>
  );
}
