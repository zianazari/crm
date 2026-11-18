"use client";

import { useState, type ReactElement } from "react";
import { Loader2, Pencil, UserPlus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { formatMobile, formatNumber } from "@/lib/format";
import { keys, useMe, useSettings } from "@/lib/queries";
import { ROLE_LABELS, type AdminUser, type OpenItems, type Role, type Team } from "@/lib/types";
import { cn } from "@/lib/utils";

async function refresh(queryClient: ReturnType<typeof useQueryClient>) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: keys.settings }),
    queryClient.invalidateQueries({ queryKey: ["users"] }),
  ]);
}

export function UsersTab({ admin }: { admin: boolean }) {
  const [showInactive, setShowInactive] = useState(false);
  const { data: users, isPending } = useSettings<AdminUser[]>("/users", { include_inactive: showInactive });
  const { data: teams = [] } = useSettings<Team[]>("/teams", {}, admin);
  const { data: me } = useMe();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {admin ? "ثبت‌نام عمومی وجود ندارد؛ کاربران فقط از اینجا ساخته می‌شوند." : "اعضای تیم شما. تغییر کاربران با ادمین است."}
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" aria-pressed={showInactive} onClick={() => setShowInactive(!showInactive)}>
            {showInactive ? "پنهان کردن غیرفعال‌ها" : "نمایش غیرفعال‌ها"}
          </Button>
          {admin ? (
            <UserFormDialog
              teams={teams}
              trigger={
                <Button>
                  <UserPlus aria-hidden />
                  کاربر جدید
                </Button>
              }
            />
          ) : null}
        </div>
      </div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>نام</TableHead>
              <TableHead>موبایل / ایمیل</TableHead>
              <TableHead>نقش</TableHead>
              <TableHead>تیم</TableHead>
              <TableHead>وضعیت</TableHead>
              {admin ? <TableHead className="w-0" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending || !users ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Skeleton className="h-24" />
                </TableCell>
              </TableRow>
            ) : (
              users.map((u) => (
                <TableRow key={u.id} className={cn(!u.is_active && "opacity-60")}>
                  <TableCell className="font-medium">
                    {u.full_name}
                    {u.manages_team ? (
                      <span className="block text-xs font-normal text-muted-foreground">سرپرست {u.manages_team.name}</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <span className="ltr-value block">{u.mobile ? formatMobile(u.mobile) : null}</span>
                    <span className="ltr-value block text-xs text-muted-foreground">{u.email}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={u.role === "admin" ? "default" : "secondary"}>{ROLE_LABELS[u.role]}</Badge>
                  </TableCell>
                  <TableCell>{u.team?.name ?? "—"}</TableCell>
                  <TableCell>{u.is_active ? "فعال" : "غیرفعال"}</TableCell>
                  {admin ? (
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <UserFormDialog
                          user={u}
                          teams={teams}
                          trigger={
                            <Button variant="ghost" size="icon-sm" aria-label={`ویرایش ${u.full_name}`}>
                              <Pencil />
                            </Button>
                          }
                        />
                        {u.id === me?.id ? null : u.is_active ? (
                          <DeactivateDialog user={u} users={users} />
                        ) : (
                          <ReactivateButton user={u} />
                        )}
                      </div>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function UserFormDialog({ user, teams, trigger }: { user?: AdminUser; teams: Team[]; trigger: ReactElement }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("sales_rep");
  const [teamId, setTeamId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function reset(next: boolean) {
    setOpen(next);
    if (next) {
      setName(user?.full_name ?? "");
      setMobile(user?.mobile ? formatMobile(user.mobile) : "");
      setEmail(user?.email ?? "");
      setRole(user?.role ?? "sales_rep");
      setTeamId(user?.team?.id ?? "");
      setError(null);
    }
  }

  async function save() {
    setPending(true);
    setError(null);
    const body = { full_name: name, mobile: mobile || null, email: email || null, role, team_id: teamId || null };
    try {
      await apiFetch(user ? `/users/${user.id}` : "/users", {
        method: user ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      await refresh(queryClient);
      toast.success(user ? "کاربر به‌روز شد." : "کاربر ساخته شد. با موبایل یا ایمیل خود وارد می‌شود.");
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{user ? "ویرایش کاربر" : "کاربر جدید"}</DialogTitle>
          <DialogDescription>ورود با کد یک‌بارمصرف به همین موبایل یا ایمیل انجام می‌شود.</DialogDescription>
        </DialogHeader>
        <form
          id="user-form"
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <Field label="نام و نام خانوادگی" htmlFor="u-name" required className="sm:col-span-2">
            <Input id="u-name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="موبایل" htmlFor="u-mobile">
            <Input id="u-mobile" dir="ltr" type="tel" className="text-start" value={mobile} onChange={(e) => setMobile(e.target.value)} placeholder="09xxxxxxxxx" />
          </Field>
          <Field label="ایمیل" htmlFor="u-email">
            <Input id="u-email" dir="ltr" type="email" className="text-start" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="نقش" htmlFor="u-role" required>
            <NativeSelect id="u-role" className="w-full" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
                <NativeSelectOption key={r} value={r}>
                  {ROLE_LABELS[r]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Field label="تیم" htmlFor="u-team">
            <NativeSelect id="u-team" className="w-full" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <NativeSelectOption value="">بدون تیم</NativeSelectOption>
              {teams.map((t) => (
                <NativeSelectOption key={t.id} value={t.id}>
                  {t.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          {user && user.role === "sales_manager" && role !== "sales_manager" && user.manages_team ? (
            <p className="text-sm text-warning-foreground sm:col-span-2">
              با تغییر نقش، سرپرستی تیم «{user.manages_team.name}» از او گرفته می‌شود.
            </p>
          ) : null}
        </form>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="submit" form="user-form" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Deactivation ends all sessions; open work is handed to someone or kept on purpose (spec 5). */
function DeactivateDialog({ user, users }: { user: AdminUser; users: AdminUser[] }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  const [leave, setLeave] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: items } = useSettings<OpenItems>(`/users/${user.id}/open-items`, {}, open);
  const total = items ? items.leads + items.customers + items.deals + items.activities : 0;

  async function deactivate() {
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/users/${user.id}/deactivate`, {
        method: "POST",
        body: JSON.stringify({ transfer_to_id: target || null, leave_open_items: !target && leave }),
      });
      await refresh(queryClient);
      toast.success(`${user.full_name} غیرفعال شد و از همه دستگاه‌ها خارج شد.`);
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setTarget("");
        setLeave(false);
        setError(null);
      }}
    >
      <DialogTrigger render={<Button variant="ghost" size="sm" className="text-destructive" />}>غیرفعال‌سازی</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>غیرفعال‌سازی {user.full_name}</DialogTitle>
          <DialogDescription>همه نشست‌های او فوراً پایان می‌یابد و دیگر نمی‌تواند وارد شود.</DialogDescription>
        </DialogHeader>
        {!items ? (
          <Skeleton className="h-16" />
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">پرونده یا کار بازی ندارد.</p>
        ) : (
          <div className="space-y-3 text-sm">
            <p>
              کارهای باز: {formatNumber(items.leads)} مشتری احتمالی، {formatNumber(items.customers)} مشتری،{" "}
              {formatNumber(items.deals)} فروش باز و {formatNumber(items.activities)} فعالیت.
            </p>
            <Field label="انتقال به" htmlFor="transfer-to">
              <NativeSelect id="transfer-to" className="w-full" value={target} onChange={(e) => setTarget(e.target.value)}>
                <NativeSelectOption value="">انتخاب کاربر</NativeSelectOption>
                {users
                  .filter((u) => u.is_active && u.id !== user.id)
                  .map((u) => (
                    <NativeSelectOption key={u.id} value={u.id}>
                      {u.full_name} — {ROLE_LABELS[u.role]}
                    </NativeSelectOption>
                  ))}
              </NativeSelect>
            </Field>
            {!target ? (
              <label className="flex items-start gap-2">
                <input type="checkbox" checked={leave} onChange={(e) => setLeave(e.target.checked)} className="mt-1" />
                بدون انتقال غیرفعال شود؛ پرونده‌ها به نام او می‌مانند و مدیر بعداً منتقلشان می‌کند.
              </label>
            ) : null}
          </div>
        )}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="destructive" disabled={pending || !items || (total > 0 && !target && !leave)} onClick={() => void deactivate()}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            غیرفعال‌سازی
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReactivateButton({ user }: { user: AdminUser }) {
  const queryClient = useQueryClient();
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={async () => {
        try {
          await apiFetch(`/users/${user.id}/reactivate`, { method: "POST" });
          await refresh(queryClient);
          toast.success(`${user.full_name} دوباره فعال شد.`);
        } catch (err) {
          toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
        }
      }}
    >
      فعال‌سازی
    </Button>
  );
}
