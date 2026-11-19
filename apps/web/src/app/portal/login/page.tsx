import type { Metadata } from "next";
import { Suspense } from "react";

import { Logo } from "@/components/layout/app-sidebar";
import { LoginForm } from "@/app/login/login-form";

export const metadata: Metadata = { title: "ورود به پنل مشتری", robots: { index: false } };

export default function PortalLoginPage() {
  return (
    <main className="grid min-h-svh place-items-center p-4">
      <div className="w-full max-w-[420px] space-y-6">
        <div className="flex justify-center">
          <Logo />
        </div>
        <section className="rounded-xl border bg-card p-6 text-card-foreground shadow-xs">
          <h1 className="text-[22px] leading-8 font-bold">پنل مشتری</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            با شماره همراه یا ایمیلی که نزد ما ثبت کرده‌اید وارد شوید تا درخواست‌های پشتیبانی خود را ثبت و پیگیری کنید.
          </p>
          <Suspense>
            <LoginForm api="/portal/auth" home="/portal" area="/portal" />
          </Suspense>
        </section>
      </div>
    </main>
  );
}
