import type { Metadata } from "next";
import { Suspense } from "react";

import { Logo } from "@/components/layout/app-sidebar";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "ورود" };

/** Sizes and spacing follow the approved login reference: 420px card, 24px padding,
 * 22px title, 14px text, 48px field and 42px button. */
export default function LoginPage() {
  return (
    <main className="grid min-h-svh place-items-center p-4">
      <div className="w-full max-w-[420px] space-y-6">
        <div className="flex justify-center">
          <Logo />
        </div>
        <section className="rounded-xl border bg-card p-6 text-card-foreground shadow-xs">
          <h1 className="text-[22px] leading-8 font-bold">ورود</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            برای ورود، ایمیل یا شماره‌ی همراه ثبت‌شده‌تان را وارد کنید.
          </p>
          <Suspense>
            <LoginForm />
          </Suspense>
        </section>
      </div>
    </main>
  );
}
