"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlarmClock, Bell, CalendarCheck, CheckCheck, Loader2, Sun, UserPlus, type LucideIcon, Inbox } from "lucide-react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "activity_reminder" | "activity_assigned" | "record_assigned" | "daily_digest" | "team_task";

type Notification = {
  id: string;
  kind: Kind;
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
  read_at: string | null;
};

type Page = { items: Notification[]; unread: number; has_more: boolean };

const ICONS: Record<Kind, LucideIcon> = {
  activity_reminder: AlarmClock,
  activity_assigned: CalendarCheck,
  record_assigned: UserPlus,
  daily_digest: Sun,
  team_task: Inbox,
};

const KEY = ["notifications"] as const;

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "همین حالا";
  if (minutes < 60) return `${formatNumber(minutes)} دقیقه پیش`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${formatNumber(hours)} ساعت پیش`;
  return `${formatNumber(Math.round(hours / 24))} روز پیش`;
}

/** In-app notifications (spec 4.2). Polls the unread count; the list loads when opened. */
export function NotificationBell() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const lastSeen = useRef<string | null>(null);

  const { data: count } = useQuery({
    queryKey: [...KEY, "count"],
    queryFn: () => apiFetch<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const unread = count?.unread ?? 0;

  // Newest unread notification, to raise a toast when a new one arrives.
  const { data: newest } = useQuery({
    queryKey: [...KEY, "newest", unread],
    queryFn: () => apiFetch<Page>("/notifications?unread_only=true&limit=1"),
    enabled: unread > 0,
  });
  useEffect(() => {
    const item = newest?.items[0];
    if (!item) return;
    if (lastSeen.current !== null && lastSeen.current !== item.id) {
      toast(item.title, { description: item.body ?? undefined });
    }
    lastSeen.current = item.id;
  }, [newest]);

  const list = useInfiniteQuery({
    queryKey: [...KEY, "list"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      apiFetch<Page>(`/notifications?limit=15${pageParam ? `&before=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: (last) => (last.has_more ? (last.items.at(-1)?.created_at ?? null) : null),
    enabled: open,
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: KEY });
  }

  async function openItem(n: Notification) {
    if (!n.read_at) await apiFetch(`/notifications/${n.id}/read`, { method: "POST" });
    setOpen(false);
    await refresh();
    if (n.link) router.push(n.link);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            aria-label={unread ? `اعلان‌ها، ${formatNumber(unread)} خوانده‌نشده` : "اعلان‌ها"}
          />
        }
      >
        <Bell className="size-5" />
        {unread ? (
          <span className="absolute -top-0.5 -end-0.5 grid min-w-4.5 place-items-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-white dark:text-background">
            {unread > 99 ? "۹۹+" : formatNumber(unread)}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="font-semibold">اعلان‌ها</p>
          {unread ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await apiFetch("/notifications/read-all", { method: "POST" });
                await refresh();
              }}
            >
              <CheckCheck aria-hidden />
              خواندن همه
            </Button>
          ) : null}
        </div>
        <div className="max-h-[26rem] overflow-y-auto">
          {list.isPending ? (
            <p className="p-6 text-center text-sm text-muted-foreground">در حال دریافت…</p>
          ) : items.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted-foreground">اعلانی ندارید.</p>
          ) : (
            <ul className="divide-y">
              {items.map((n) => {
                const Icon = ICONS[n.kind];
                return (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => void openItem(n)}
                      className={cn("flex w-full gap-3 px-4 py-3 text-start hover:bg-muted", !n.read_at && "bg-accent/40")}
                    >
                      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
                        <Icon className="size-4" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1 space-y-0.5">
                        <span className={cn("block text-sm", !n.read_at && "font-semibold")}>{n.title}</span>
                        {n.body ? <span className="block text-xs text-muted-foreground">{n.body}</span> : null}
                        <span className="block text-xs text-muted-foreground">{ago(n.created_at)}</span>
                      </span>
                      {!n.read_at ? (
                        <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="خوانده‌نشده" />
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {list.hasNextPage ? (
            <div className="border-t p-2 text-center">
              <Button variant="ghost" size="sm" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
                {list.isFetchingNextPage ? <Loader2 className="animate-spin" aria-hidden /> : null}
                قدیمی‌تر
              </Button>
            </div>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
