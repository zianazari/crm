"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronLeft, Lock } from "lucide-react";

import { Owner } from "@/components/crm/bits";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { UserRef } from "@/lib/types";

export function Breadcrumb({ href, label, current }: { href: string; label: string; current: string }) {
  return (
    <nav aria-label="مسیر" className="flex items-center gap-1 text-sm text-muted-foreground">
      <Link href={href} className="hover:text-foreground">
        {label}
      </Link>
      <ChevronLeft className="size-4" aria-hidden />
      <span className="text-foreground">{current}</span>
    </nav>
  );
}

export function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Skeleton className="h-64" />
        <Skeleton className="order-first h-80 lg:order-last" />
      </div>
    </div>
  );
}

export function DetailError({ error }: { error: Error }) {
  const notFound = error instanceof ApiError && error.status === 404;
  return (
    <Alert variant="destructive">
      <AlertTitle>{notFound ? "پرونده پیدا نشد" : "خطا در دریافت اطلاعات"}</AlertTitle>
      <AlertDescription>{notFound ? "ممکن است بایگانی یا حذف شده باشد." : error.message}</AlertDescription>
    </Alert>
  );
}

/** What a user sees of a record they do not own (spec section 0, decision 4). */
export function LimitedRecord({
  title,
  owner,
  status,
  lastActivity,
}: {
  title: string;
  owner: UserRef;
  status?: ReactNode;
  lastActivity: string | null;
}) {
  return (
    <Card className="max-w-xl">
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          {status}
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <dt className="text-muted-foreground">مسئول</dt>
          <dd>
            <Owner user={owner} />
          </dd>
          <dt className="text-muted-foreground">آخرین فعالیت</dt>
          <dd>{formatDate(lastActivity)}</dd>
        </dl>
        <Alert>
          <Lock aria-hidden />
          <AlertTitle>فقط وضعیت فعلی</AlertTitle>
          <AlertDescription>
            این پرونده متعلق به {owner.full_name} است. برای جزئیات یا پیگیری با مسئول پرونده یا مدیر هماهنگ
            کنید.
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}
