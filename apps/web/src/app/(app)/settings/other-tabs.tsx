"use client";

import { useState, type ReactElement } from "react";
import { ArrowDown, ArrowUp, Loader2, Pencil, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Pagination } from "@/components/crm/list-parts";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { keys, useSettings } from "@/lib/queries";
import type { AdminUser, AuditEntry, LeadSource, Page, Stage, Team } from "@/lib/types";
import { cn } from "@/lib/utils";

function useAction() {
  const queryClient = useQueryClient();
  return async (path: string, method: string, body: unknown, message: string): Promise<boolean> => {
    try {
      await apiFetch(path, { method, body: JSON.stringify(body) });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.settings }),
        queryClient.invalidateQueries({ queryKey: ["stages"] }),
        queryClient.invalidateQueries({ queryKey: ["lead-sources"] }),
        queryClient.invalidateQueries({ queryKey: keys.deals }),
      ]);
      toast.success(message);
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
      return false;
    }
  };
}

/** A small dialog with a single name field (and optional extra content). */
function NameDialog({
  title,
  initial = "",
  trigger,
  onSave,
  children,
}: {
  title: string;
  initial?: string;
  trigger: ReactElement;
  onSave: (name: string) => Promise<boolean>;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(initial);
  const [pending, setPending] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setName(initial);
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">{title}</DialogDescription>
        </DialogHeader>
        <form
          id="name-form"
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setPending(true);
            const ok = await onSave(name.trim());
            setPending(false);
            if (ok) setOpen(false);
          }}
        >
          <Field label="نام" htmlFor="name-input" required>
            <Input id="name-input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          {children}
        </form>
        <DialogFooter>
          <Button type="submit" form="name-form" disabled={pending || name.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -- teams ---------------------------------------------------------------------

export function TeamsTab({ admin }: { admin: boolean }) {
  const { data: teams, isPending } = useSettings<Team[]>("/teams");
  const { data: users = [] } = useSettings<AdminUser[]>("/users", {}, admin);
  const managers = users.filter((u) => u.role === "sales_manager");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">هر مدیر فروش سرپرست فقط یک تیم است. اعضا از ویرایش کاربر به تیم اضافه می‌شوند.</p>
        {admin ? <TeamDialog managers={managers} trigger={<Button><Plus aria-hidden />تیم جدید</Button>} /> : null}
      </div>
      {isPending || !teams ? (
        <Skeleton className="h-24" />
      ) : teams.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">هنوز تیمی تعریف نشده است.</CardContent></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {teams.map((t) => (
            <Card key={t.id} className={cn(!t.is_active && "opacity-60")}>
              <CardContent className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold">{t.name}</p>
                  {admin ? (
                    <TeamDialog
                      team={t}
                      managers={managers}
                      trigger={<Button variant="ghost" size="icon-sm" aria-label={`ویرایش ${t.name}`}><Pencil /></Button>}
                    />
                  ) : null}
                </div>
                <p className="text-sm text-muted-foreground">سرپرست: {t.manager?.full_name ?? "تعیین نشده"}</p>
                <p className="text-sm text-muted-foreground">{formatNumber(t.member_count)} عضو فعال</p>
                {!t.is_active ? <Badge variant="outline">غیرفعال</Badge> : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamDialog({ team, managers, trigger }: { team?: Team; managers: AdminUser[]; trigger: ReactElement }) {
  const act = useAction();
  const [managerId, setManagerId] = useState(team?.manager?.id ?? "");
  const [active, setActive] = useState(team?.is_active ?? true);
  return (
    <NameDialog
      title={team ? "ویرایش تیم" : "تیم جدید"}
      initial={team?.name}
      trigger={trigger}
      onSave={(name) =>
        act(team ? `/teams/${team.id}` : "/teams", team ? "PATCH" : "POST", { name, manager_id: managerId || null, is_active: active }, "تیم ذخیره شد.")
      }
    >
      <Field label="سرپرست تیم" htmlFor="team-manager" hint="فقط کاربران با نقش مدیر فروش.">
        <NativeSelect id="team-manager" className="w-full" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
          <NativeSelectOption value="">بدون سرپرست</NativeSelectOption>
          {managers.map((m) => (
            <NativeSelectOption key={m.id} value={m.id}>
              {m.full_name}
              {m.manages_team && m.manages_team.id !== team?.id ? ` (سرپرست ${m.manages_team.name})` : ""}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Field>
      {team ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          تیم فعال است
        </label>
      ) : null}
    </NameDialog>
  );
}

// -- stages ----------------------------------------------------------------------

export function StagesTab() {
  const act = useAction();
  const { data: stages, isPending } = useSettings<Stage[]>("/stages", { include_inactive: true });
  const active = (stages ?? []).filter((s) => s.is_active);
  const inactive = (stages ?? []).filter((s) => !s.is_active);

  async function swap(a: Stage, b: Stage) {
    await act(`/stages/${a.id}`, "PATCH", { name: a.name, sort_order: b.sort_order }, "ترتیب به‌روز شد.");
    await act(`/stages/${b.id}`, "PATCH", { name: b.name, sort_order: a.sort_order === b.sort_order ? a.sort_order + 1 : a.sort_order }, "ترتیب به‌روز شد.");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          مراحل باز مسیر فروش. «فروش انجام شد» و «به نتیجه نرسید» نتیجه‌اند، نه مرحله، و همیشه در ستون آخر تابلو هستند.
        </p>
        <NameDialog
          title="مرحله جدید"
          trigger={<Button><Plus aria-hidden />مرحله جدید</Button>}
          onSave={(name) => act("/stages", "POST", { name, sort_order: (active.at(-1)?.sort_order ?? 0) + 1 }, "مرحله اضافه شد.")}
        />
      </div>
      {isPending ? (
        <Skeleton className="h-40" />
      ) : (
        <Card className="py-0">
          <ol className="divide-y">
            {active.map((s, i) => (
              <li key={s.id} className="flex items-center gap-3 px-4 py-3">
                <span className="grid size-7 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                  {formatNumber(i + 1)}
                </span>
                <span className="flex-1 font-medium">{s.name}</span>
                <Button variant="ghost" size="icon-sm" aria-label={`انتقال ${s.name} به بالا`} disabled={i === 0} onClick={() => void swap(s, active[i - 1])}>
                  <ArrowUp />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label={`انتقال ${s.name} به پایین`} disabled={i === active.length - 1} onClick={() => void swap(s, active[i + 1])}>
                  <ArrowDown />
                </Button>
                <NameDialog
                  title="تغییر نام مرحله"
                  initial={s.name}
                  trigger={<Button variant="ghost" size="icon-sm" aria-label={`تغییر نام ${s.name}`}><Pencil /></Button>}
                  onSave={(name) => act(`/stages/${s.id}`, "PATCH", { name, sort_order: s.sort_order }, "نام مرحله تغییر کرد.")}
                />
                <RetireStage stage={s} others={active.filter((x) => x.id !== s.id)} disabled={active.length <= 1} />
              </li>
            ))}
          </ol>
        </Card>
      )}
      {inactive.length ? (
        <p className="text-xs text-muted-foreground">مراحل غیرفعال: {inactive.map((s) => s.name).join("، ")}</p>
      ) : null}
    </div>
  );
}

/** Retiring a stage with open deals requires choosing where those deals go (spec 4.3). */
function RetireStage({ stage, others, disabled }: { stage: Stage; others: Stage[]; disabled: boolean }) {
  const act = useAction();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); setTarget(""); }}>
      <DialogTrigger render={<Button variant="ghost" size="sm" className="text-destructive" disabled={disabled} />}>غیرفعال</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>غیرفعال‌سازی «{stage.name}»</DialogTitle>
          <DialogDescription>اگر فروش بازی در این مرحله باشد، به مرحله انتخابی منتقل و در تاریخچه ثبت می‌شود.</DialogDescription>
        </DialogHeader>
        <Field label="انتقال فروش‌های باز به" htmlFor="retire-target">
          <NativeSelect id="retire-target" className="w-full" value={target} onChange={(e) => setTarget(e.target.value)}>
            <NativeSelectOption value="">این مرحله فروش باز ندارد</NativeSelectOption>
            {others.map((o) => (
              <NativeSelectOption key={o.id} value={o.id}>{o.name}</NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <DialogFooter>
          <Button
            variant="destructive"
            onClick={async () => {
              const ok = await act(`/stages/${stage.id}/deactivate`, "POST", { move_to_stage_id: target || null }, "مرحله غیرفعال شد.");
              if (ok) setOpen(false);
            }}
          >
            غیرفعال‌سازی
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -- lead sources ------------------------------------------------------------------

export function SourcesTab() {
  const act = useAction();
  const { data: sources, isPending } = useSettings<LeadSource[]>("/lead-sources", { include_inactive: true });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">منابع جذب در فرم‌ها و گزارش «فروش به تفکیک منبع» استفاده می‌شوند. منبع حذف نمی‌شود، غیرفعال می‌شود.</p>
        <NameDialog
          title="منبع جدید"
          trigger={<Button><Plus aria-hidden />منبع جدید</Button>}
          onSave={(name) => act("/lead-sources", "POST", { name, is_active: true, sort_order: (sources?.length ?? 0) + 1 }, "منبع اضافه شد.")}
        />
      </div>
      {isPending || !sources ? (
        <Skeleton className="h-40" />
      ) : (
        <Card className="py-0">
          <ul className="divide-y">
            {sources.map((s) => (
              <li key={s.id} className={cn("flex items-center gap-3 px-4 py-3", !s.is_active && "opacity-60")}>
                <span className="flex-1 font-medium">{s.name}</span>
                {!s.is_active ? <Badge variant="outline">غیرفعال</Badge> : null}
                <NameDialog
                  title="تغییر نام منبع"
                  initial={s.name}
                  trigger={<Button variant="ghost" size="icon-sm" aria-label={`تغییر نام ${s.name}`}><Pencil /></Button>}
                  onSave={(name) => act(`/lead-sources/${s.id}`, "PATCH", { name, is_active: s.is_active, sort_order: s.sort_order }, "منبع به‌روز شد.")}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    void act(`/lead-sources/${s.id}`, "PATCH", { name: s.name, is_active: !s.is_active, sort_order: s.sort_order }, s.is_active ? "منبع غیرفعال شد." : "منبع فعال شد.")
                  }
                >
                  {s.is_active ? "غیرفعال" : "فعال"}
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// -- audit -----------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  "auth.login": "ورود",
  "auth.logout": "خروج",
  "user.created": "ساخت کاربر",
  "user.updated": "ویرایش کاربر",
  "user.deactivated": "غیرفعال‌سازی کاربر",
  "user.reactivated": "فعال‌سازی دوباره کاربر",
  "team.created": "ساخت تیم",
  "team.updated": "ویرایش تیم",
  "stage.created": "افزودن مرحله",
  "stage.updated": "ویرایش مرحله",
  "stage.deactivated": "غیرفعال‌سازی مرحله",
  "source.created": "افزودن منبع",
  "source.updated": "ویرایش منبع",
};

const FILTERS = [
  { value: "", label: "همه رویدادها" },
  { value: "auth.", label: "ورود و خروج" },
  { value: "user.", label: "کاربران و نقش‌ها" },
  { value: "team.", label: "تیم‌ها" },
  { value: "stage.", label: "مراحل فروش" },
  { value: "source.", label: "منابع جذب" },
];

export function AuditTab() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const { data, isPending } = useSettings<Page<AuditEntry>>("/audit", { action, page });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">سوابق فقط اضافه می‌شوند و قابل ویرایش یا حذف نیستند.</p>
        <NativeSelect aria-label="نوع رویداد" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
          {FILTERS.map((f) => (
            <NativeSelectOption key={f.value} value={f.value}>{f.label}</NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>زمان</TableHead>
              <TableHead>انجام‌دهنده</TableHead>
              <TableHead>رویداد</TableHead>
              <TableHead>جزئیات</TableHead>
              <TableHead>IP</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending || !data ? (
              <TableRow><TableCell colSpan={5}><Skeleton className="h-24" /></TableCell></TableRow>
            ) : data.items.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">رویدادی ثبت نشده است.</TableCell></TableRow>
            ) : (
              data.items.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap">{formatDateTime(e.at)}</TableCell>
                  <TableCell>{e.actor?.full_name ?? "—"}</TableCell>
                  <TableCell>{ACTION_LABELS[e.action] ?? e.action}</TableCell>
                  <TableCell className="max-w-72 truncate text-xs text-muted-foreground" title={e.details ? JSON.stringify(e.details) : undefined}>
                    <span dir="ltr">{e.details ? JSON.stringify(e.details) : "—"}</span>
                  </TableCell>
                  <TableCell className="ltr-value text-xs">{e.ip_address ?? "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
      {data && data.total > data.page_size ? <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} /> : null}
    </div>
  );
}
