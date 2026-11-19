"use client";

import { useEffect, useState } from "react";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { apiFetch, fetchMe, redirectToLogin, type CurrentUser } from "@/lib/api";
import { setTheme, useThemeChoice, type ThemeChoice } from "@/lib/theme";

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

  const theme = useThemeChoice();
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
        {/* Base UI only allows a menu label inside a group. */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="space-y-0.5 py-2">
            <div className="text-sm font-semibold text-foreground">{user.full_name}</div>
            <div className="text-xs">{ROLE_LABELS[user.role]}</div>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>ظاهر</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemeChoice)}>
            <DropdownMenuRadioItem value="light">
              <Sun aria-hidden />
              روشن
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">
              <Moon aria-hidden />
              تیره
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system">
              <Monitor aria-hidden />
              مطابق دستگاه
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void logout()}>
          <LogOut aria-hidden />
          خروج
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
