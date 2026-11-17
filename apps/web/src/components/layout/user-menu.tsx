"use client";

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { apiFetch, fetchMe, redirectToLogin, type CurrentUser } from "@/lib/api";

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  admin: "ادمین",
  sales_manager: "مدیر فروش",
  sales_rep: "کارشناس فروش",
};

function initials(name: string): string {
  // Persian letters join when adjacent, so a single letter reads more cleanly.
  return name.trim().charAt(0);
}

export function UserMenu() {
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    fetchMe()
      .then(setUser)
      .catch(() => redirectToLogin());
  }, []);

  async function logout() {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } finally {
      // Full reload on purpose: drop every piece of client state from the old session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    }
  }

  if (!user) return <div className="size-9 animate-pulse rounded-full bg-muted" aria-hidden />;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="حساب کاربری"
        className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <Avatar className="size-9">
          <AvatarFallback className="bg-accent text-accent-foreground">{initials(user.full_name)}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="space-y-0.5 py-2">
          <div className="text-sm font-semibold text-foreground">{user.full_name}</div>
          <div className="text-xs">{ROLE_LABELS[user.role]}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void logout()}>
          <LogOut aria-hidden />
          خروج
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
