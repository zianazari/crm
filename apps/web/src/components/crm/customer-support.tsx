"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LifeBuoy } from "lucide-react";
import { toast } from "sonner";

import { TicketStatusBadge } from "@/components/crm/ticket-bits";
import { NewTicketDialog } from "@/app/(app)/tickets/tickets-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime, formatMobile, formatNumber, formatCode } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { PortalAccess, Ticket } from "@/lib/tickets";
import type { CustomerFull, Page } from "@/lib/types";
import { useHydrated } from "@/lib/use-hydrated";

/** Portal access and tickets on a customer's record (spec 4.9). */
export function CustomerSupport({ customer, editable }: { customer: CustomerFull; editable: boolean }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const hydrated = useHydrated();
  const access = useQuery({
    queryKey: ["portal-access", customer.id],
    queryFn: () => apiFetch<PortalAccess[]>(`/portal-access?customer_id=${customer.id}`),
  });
  const tickets = useQuery({
    queryKey: ["tickets", "customer", customer.id],
    queryFn: () => apiFetch<Page<Ticket>>(`/tickets${toQuery({ customer_id: customer.id, status: "all", page_size: 5 })}`),
  });

  async function act(key: string, path: string, body: unknown, message: string) {
    setBusy(key);
    try {
      await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      toast.success(message);
      await queryClient.invalidateQueries({ queryKey: ["portal-access", customer.id] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
    } finally {
      setBusy(null);
    }
  }

  const rows = access.data ?? [];
  const active = (channel: "sms" | "email") => rows.find((r) => r.channel === channel && r.is_active);
  const channels = [
    { channel: "sms" as const, label: "موبایل", address: customer.mobile },
    { channel: "email" as const, label: "ایمیل", address: customer.email },
  ];

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <LifeBuoy className="size-5" aria-hidden />
          پنل مشتری و تیکت‌ها
        </CardTitle>
        {editable ? <NewTicketDialog customer={customer} /> : null}
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="space-y-2">
          <p className="font-medium">ورود به پنل مشتری</p>
          <ul className="space-y-2">
            {channels.map(({ channel, label, address }) => {
              const on = active(channel);
              return (
                <li key={channel} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2">
                  <span>
                    {label}:{" "}
                    <bdi dir="ltr" className="text-muted-foreground">
                      {address ? (channel === "sms" ? formatMobile(address) : address) : "ثبت نشده"}
                    </bdi>
                    {on ? (
                      <span className="ms-2 text-xs text-emerald-700">
                        فعال{on.last_login_at ? ` · آخرین ورود ${formatDateTime(on.last_login_at)}` : " · هنوز وارد نشده"}
                      </span>
                    ) : null}
                  </span>
                  {editable && address ? (
                    on ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        disabled={busy !== null}
                        onClick={() => void act(channel, `/portal-access/${on.id}/disable`, null, "دسترسی پنل غیرفعال شد و نشست‌های مشتری بسته شد.")}
                      >
                        {busy === channel ? <Loader2 className="animate-spin" aria-hidden /> : null}
                        غیرفعال‌کردن
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy !== null}
                        onClick={() =>
                          void act(channel, "/portal-access", { customer_id: customer.id, channel }, "مشتری اکنون با همین نشانی وارد پنل می‌شود.")
                        }
                      >
                        {busy === channel ? <Loader2 className="animate-spin" aria-hidden /> : null}
                        فعال‌کردن
                      </Button>
                    )
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-muted-foreground">
            نشانی پنل: <bdi dir="ltr">{hydrated ? `${window.location.origin}/portal` : "/portal"}</bdi> — مشتری با کد
            یک‌بارمصرف وارد می‌شود و فقط درخواست‌های خودش را می‌بیند.
          </p>
        </div>
        <div className="space-y-2 border-t pt-3">
          <p className="font-medium">تیکت‌های اخیر</p>
          {!tickets.data ? null : tickets.data.items.length === 0 ? (
            <p className="text-muted-foreground">تیکتی ثبت نشده است.</p>
          ) : (
            <ul className="space-y-1">
              {tickets.data.items.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2">
                  <Link href={`/tickets/${t.id}`} className="truncate hover:underline">
                    {formatCode(t.number)} — {t.subject}
                  </Link>
                  <TicketStatusBadge status={t.status} />
                </li>
              ))}
            </ul>
          )}
          {tickets.data && tickets.data.total > tickets.data.items.length ? (
            <Link href="/tickets" className="text-xs text-primary hover:underline">
              همه {formatNumber(tickets.data.total)} تیکت
            </Link>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
