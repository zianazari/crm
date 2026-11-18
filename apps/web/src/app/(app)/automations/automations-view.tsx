"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FilePlus2, Loader2, Plus, ShieldAlert, Workflow } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, apiFetch } from "@/lib/api";
import { EVENT_LABELS, type RuleDetail, type RuleSummary, type Template } from "@/lib/automation";
import { formatDateTime, formatNumber } from "@/lib/format";
import { canManage, useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { RuleStatusBadge } from "./parts";

export function useRules(enabled: boolean) {
  return useQuery({
    queryKey: ["automations", "list"],
    queryFn: () => apiFetch<RuleSummary[]>("/automations"),
    enabled,
  });
}

export function AutomationsView() {
  const { data: me, isPending } = useMe();
  const manager = canManage(me?.role);
  const { data: rules, isPending: loading } = useRules(manager);

  if (isPending || !me) return <Skeleton className="h-96" />;
  if (!manager) {
    return (
      <>
        <PageHeader title="اتوماسیون" />
        <Alert>
          <ShieldAlert aria-hidden />
          <AlertTitle>دسترسی به اتوماسیون ندارید</AlertTitle>
          <AlertDescription>ساخت و مدیریت اتوماسیون با مدیر فروش و ادمین است.</AlertDescription>
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="اتوماسیون"
        description="جریان‌های خودکار: با هر رویداد، شرط‌ها بررسی و اقدام‌ها به ترتیب اجرا می‌شوند."
        actions={<NewRuleDialog />}
      />
      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>نام</TableHead>
                <TableHead>رویداد شروع</TableHead>
                <TableHead>وضعیت</TableHead>
                <TableHead>نسخه فعال</TableHead>
                <TableHead>اجرا در ۳۰ روز</TableHead>
                <TableHead>سازنده</TableHead>
                <TableHead>آخرین تغییر</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading || !rules ? (
                Array.from({ length: 3 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-5" />
                    </TableCell>
                  </TableRow>
                ))
              ) : rules.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-14 text-center">
                    <Workflow className="mx-auto mb-3 size-8 text-muted-foreground" aria-hidden />
                    <p className="font-medium">هنوز اتوماسیونی نساخته‌اید</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      با «اتوماسیون جدید» از یک قالب آماده یا صفحه خالی شروع کنید.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                rules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="max-w-72">
                      <Link href={`/automations/${rule.id}`} className="font-medium hover:underline">
                        {rule.name}
                      </Link>
                      {rule.description ? (
                        <p className="truncate text-xs text-muted-foreground">{rule.description}</p>
                      ) : null}
                    </TableCell>
                    <TableCell>{rule.trigger_event ? EVENT_LABELS[rule.trigger_event] ?? rule.trigger_event : "—"}</TableCell>
                    <TableCell>
                      <RuleStatusBadge status={rule.status} />
                    </TableCell>
                    <TableCell>{rule.active_version ? formatNumber(rule.active_version.number) : "—"}</TableCell>
                    <TableCell>
                      {formatNumber(rule.runs_last_30_days)}
                      {rule.failures_last_30_days ? (
                        <span className="ms-2 text-xs text-destructive">
                          {formatNumber(rule.failures_last_30_days)} ناموفق
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>{rule.created_by.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(rule.updated_at)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}

function NewRuleDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<string>("");
  const [pending, setPending] = useState(false);
  const { data: templates } = useQuery({
    queryKey: ["automations", "templates"],
    queryFn: () => apiFetch<Template[]>("/automations/templates"),
    enabled: open,
    staleTime: Infinity,
  });

  function choose(key: string) {
    setTemplate(key);
    const chosen = templates?.find((t) => t.key === key);
    if (chosen && (!name || templates?.some((t) => t.name === name))) setName(chosen.name);
  }

  async function create() {
    setPending(true);
    try {
      const rule = await apiFetch<RuleDetail>("/automations", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), template: template || null }),
      });
      router.push(`/automations/${rule.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ساخت اتوماسیون انجام نشد.");
      setPending(false);
    }
  }

  const options = [
    { key: "", name: "صفحه خالی", description: "بلوک‌ها را خودتان از ابتدا بچینید." },
    ...(templates ?? []),
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setName("");
          setTemplate("");
          setPending(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button>
            <Plus aria-hidden />
            اتوماسیون جدید
          </Button>
        }
      />
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>اتوماسیون جدید</DialogTitle>
          <DialogDescription>یک قالب آماده انتخاب کنید یا از صفحه خالی شروع کنید. تا انتشار، چیزی اجرا نمی‌شود.</DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="نقطه شروع" className="grid max-h-[50vh] gap-2 overflow-y-auto sm:grid-cols-2">
          {!templates
            ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-20" />)
            : options.map((option) => (
                <button
                  key={option.key || "blank"}
                  type="button"
                  role="radio"
                  aria-checked={template === option.key}
                  onClick={() => choose(option.key)}
                  className={cn(
                    "rounded-lg border p-3 text-start transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
                    template === option.key && "border-primary bg-accent/60 ring-1 ring-primary",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    {option.key ? <Workflow className="size-4 text-primary" aria-hidden /> : <FilePlus2 className="size-4" aria-hidden />}
                    {option.name}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">{option.description}</span>
                </button>
              ))}
        </div>
        <Field label="نام اتوماسیون" htmlFor="rule-name" required>
          <Input id="rule-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button onClick={() => void create()} disabled={pending || name.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ساخت و باز کردن سازنده
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
