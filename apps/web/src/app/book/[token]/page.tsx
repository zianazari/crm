import type { Metadata } from "next";
import { Suspense } from "react";

import { Logo } from "@/components/layout/app-sidebar";
import { Providers } from "@/components/providers";
import { BookingPage } from "./booking-page";

export const metadata: Metadata = {
  title: "انتخاب زمان جلسه",
  robots: { index: false },
};

export default function Page({ params }: PageProps<"/book/[token]">) {
  return (
    <Providers>
      <main className="min-h-svh bg-background px-4 py-8">
        <div className="mx-auto w-full max-w-xl space-y-6">
          <div className="flex justify-center">
            <Logo />
          </div>
          <Suspense fallback={null}>
            <TokenLoader params={params} />
          </Suspense>
        </div>
      </main>
    </Providers>
  );
}

async function TokenLoader({
  params,
}: {
  params: PageProps<"/book/[token]">["params"];
}) {
  const { token } = await params;
  return <BookingPage token={token} />;
}
