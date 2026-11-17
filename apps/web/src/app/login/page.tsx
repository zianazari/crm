import type { Metadata } from "next";
import { Suspense } from "react";

import { Logo } from "@/components/layout/app-sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "ورود" };

export default function LoginPage() {
  return (
    <main className="grid min-h-svh place-items-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Logo />
        </div>
        <Card>
          <CardContent className="space-y-6 py-6">
            <div className="space-y-1">
              <h1 className="text-xl font-bold">ورود به سامانه</h1>
              <p className="text-sm text-muted-foreground">
                کد یک‌بارمصرف به موبایل یا ایمیل ثبت‌شده شما ارسال می‌شود.
              </p>
            </div>
            <Suspense>
              <LoginForm />
            </Suspense>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
