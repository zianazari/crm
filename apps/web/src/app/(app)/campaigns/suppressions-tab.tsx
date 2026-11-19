"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { EmptyRow, Pagination, SearchInput, SkeletonRows } from "@/components/crm/list-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { CHANNEL_LABELS, type Channel, type Suppression } from "@/lib/campaigns";
import { formatDateTime, formatMobile } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { Page } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";

const KEY = ["suppressions"] as const;

/** The do-not-send list: marketing never goes to these addresses (spec 4.5). */
export function SuppressionsTab({ admin }: { admin: boolean }) {
  const queryClient = useQueryClient();
  const [channel, setChannel] = useState<Channel | "">("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const search = useDebounced(q, 300);
  const { data, isPending } = useQuery({
    queryKey: [...KEY, channel, search, page],
    queryFn: () => apiFetch<Page<Suppression>>(`/suppressions${toQuery({ channel, q: search, page, page_size: 50 })}`),
    placeholderData: (previous) => previous,
  });

  async function remove(row: Suppression) {
    try {
      await apiFetch(`/suppressions/${row.id}`, { method: "DELETE" });
      toast.success("از فهرست حذف شد. پیام تبلیغاتی فقط با اجازه دوباره مخاطب فرستاده می‌شود.");
      await queryClient.invalidateQueries({ queryKey: KEY });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="جست‌وجوی نشانی" />
          <NativeSelect
            aria-label="کانال"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value as Channel | "");
              setPage(1);
            }}
          >
            <NativeSelectOption value="">همه کانال‌ها</NativeSelectOption>
            <NativeSelectOption value="sms">پیامک</NativeSelectOption>
            <NativeSelectOption value="email">ایمیل</NativeSelectOption>
          </NativeSelect>
        </div>
        <AddDialog />
      </div>
      <p className="text-sm text-muted-foreground">
        مخاطبانی که از پیوند لغو استفاده کرده‌اند خودکار اینجا قرار می‌گیرند. پیام‌های عملیاتی مانند کد ورود تابع این فهرست نیستند.
      </p>
      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>نشانی</TableHead>
                <TableHead>کانال</TableHead>
                <TableHead>علت</TableHead>
                <TableHead>توضیح</TableHead>
                <TableHead>تاریخ</TableHead>
                {admin ? <TableHead><span className="sr-only">حذف</span></TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending || !data ? (
                <SkeletonRows columns={admin ? 6 : 5} rows={3} />
              ) : data.items.length === 0 ? (
                <EmptyRow columns={admin ? 6 : 5}>نشانی‌ای در فهرست نیست.</EmptyRow>
              ) : (
                data.items.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <span className="ltr-value">{row.channel === "sms" ? formatMobile(row.address) : row.address}</span>
                    </TableCell>
                    <TableCell>{CHANNEL_LABELS[row.channel]}</TableCell>
                    <TableCell>
                      <Badge variant={row.reason === "unsubscribed" ? "secondary" : "outline"}>
                        {row.reason === "unsubscribed" ? "لغو توسط مخاطب" : "افزوده‌شده توسط کاربر"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{row.note ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(row.created_at)}</TableCell>
                    {admin ? (
                      <TableCell>
                        <Button variant="ghost" size="icon-sm" aria-label={`حذف ${row.address} از فهرست`} onClick={() => void remove(row)}>
                          <Trash2 />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && data.total > data.page_size ? (
        <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      ) : null}
    </div>
  );
}

function AddDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<Channel>("sms");
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);

  async function add() {
    setPending(true);
    try {
      await apiFetch("/suppressions", { method: "POST", body: JSON.stringify({ channel, address, note: note || null }) });
      toast.success("به فهرست عدم ارسال افزوده شد.");
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: KEY });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setAddress("");
          setNote("");
        }
      }}
    >
      <DialogTrigger
        render={
          <Button variant="outline">
            <Plus aria-hidden />
            افزودن نشانی
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>افزودن به فهرست عدم ارسال</DialogTitle>
          <DialogDescription>برای مخاطبی که خارج از سامانه (مثلاً تلفنی) درخواست کرده پیام تبلیغاتی نگیرد.</DialogDescription>
        </DialogHeader>
        <Field label="کانال" htmlFor="sup-channel">
          <NativeSelect id="sup-channel" className="w-full" value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
            <NativeSelectOption value="sms">پیامک</NativeSelectOption>
            <NativeSelectOption value="email">ایمیل</NativeSelectOption>
          </NativeSelect>
        </Field>
        <Field label={channel === "sms" ? "شماره موبایل" : "ایمیل"} htmlFor="sup-address" required>
          <Input id="sup-address" dir="ltr" value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field label="توضیح" htmlFor="sup-note">
          <Input id="sup-note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button onClick={() => void add()} disabled={pending || address.trim().length < 3}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            افزودن
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
