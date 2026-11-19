"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Camera, ChevronDown, LogOut } from "lucide-react";

import { UserAvatar } from "@/components/crm/user-avatar";
import { ProfilePhotoDialog } from "@/components/layout/profile-photo-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  apiFetch,
  fetchMe,
  redirectToLogin,
  type CurrentUser,
} from "@/lib/api";

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  admin: "ادمین",
  sales_manager: "مدیر فروش",
  sales_rep: "کارشناس فروش",
};

export function UserMenu() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [photoOpen, setPhotoOpen] = useState(false);
  const queryClient = useQueryClient();

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

  if (!user)
    return (
      <div className="size-9 animate-pulse rounded-full bg-muted" aria-hidden />
    );

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="حساب کاربری"
          className="flex items-center gap-1 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <UserAvatar user={user} className="size-9 text-base" />
          <ChevronDown className="size-4 text-muted-foreground" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {/* Base UI only allows a menu label inside a group. */}
          <DropdownMenuGroup>
            <DropdownMenuLabel className="space-y-0.5 py-2">
              <div className="text-sm font-semibold text-foreground">
                {user.full_name}
              </div>
              <div className="text-xs">{ROLE_LABELS[user.role]}</div>
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setPhotoOpen(true)}>
            <Camera aria-hidden />
            تصویر پروفایل
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void logout()}>
            <LogOut aria-hidden />
            خروج
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ProfilePhotoDialog
        user={user}
        open={photoOpen}
        onOpenChange={setPhotoOpen}
        onSaved={(next) => {
          setUser(next);
          // Every list that shows this person picks up the new photo.
          void queryClient.invalidateQueries();
        }}
      />
    </>
  );
}
