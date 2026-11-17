"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Toaster } from "@/components/ui/sonner";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            // Permission and not-found answers will not change on retry.
            retry: (count, error) =>
              !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 2,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster position="top-center" dir="rtl" theme="light" richColors />
    </QueryClientProvider>
  );
}
