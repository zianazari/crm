"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";

import { ThemeMenu } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { portalFetch, type PortalMe } from "@/lib/portal";

export function usePortalMe() {
  return useQuery({ queryKey: ["portal", "me"], queryFn: () => portalFetch<PortalMe>("/me"), staleTime: 5 * 60_000 });
}

export function PortalHeader() {
  const { data: me } = usePortalMe();
  async function logout() {
    try {
      await portalFetch("/auth/logout", { method: "POST" });
    } finally {
      // Full reload on purpose: nothing of the ended session stays in memory.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/portal/login");
    }
  }
  return (
    <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-3xl items-center gap-3 px-4 md:px-6">
        <Link href="/portal" className="flex items-center gap-2">
          <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <svg viewBox="0 0 24 24" className="size-5" fill="currentColor">
              <path d="M14.5 3 21 9.5 9.5 21 3 14.5z" opacity=".55" />
              <path d="M14.5 3 21 9.5l-4 4L10.5 7z" />
            </svg>
          </span>
          <span className="font-bold">پنل مشتری</span>
        </Link>
        <span className="ms-auto truncate text-sm text-muted-foreground">{me?.customer_name}</span>
        <ThemeMenu />
        <Button variant="ghost" size="sm" onClick={() => void logout()}>
          <LogOut aria-hidden />
          خروج
        </Button>
      </div>
    </header>
  );
}
