"use client";

import { useState } from "react";
import { GitBranch, Link2, ScrollText, ShieldAlert, UserCog, Users } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { AuditTab, SourcesTab, StagesTab, TeamsTab } from "./other-tabs";
import { UsersTab } from "./users-tab";

type TabKey = "users" | "teams" | "stages" | "sources" | "audit";

const TABS: { key: TabKey; label: string; icon: typeof Users; roles: string[] }[] = [
  { key: "users", label: "کاربران", icon: UserCog, roles: ["admin", "sales_manager"] },
  { key: "teams", label: "تیم‌ها", icon: Users, roles: ["admin", "sales_manager"] },
  { key: "stages", label: "مراحل فروش", icon: GitBranch, roles: ["admin", "sales_manager"] },
  { key: "sources", label: "منابع جذب", icon: Link2, roles: ["admin"] },
  { key: "audit", label: "سوابق ممیزی", icon: ScrollText, roles: ["admin"] },
];

/** Tabs follow spec 5: admins manage everything; managers see their team and set the
 * pipeline stages; reps have no settings. The API enforces the same rules. */
export function SettingsView() {
  const { data: me, isPending } = useMe();
  const [tab, setTab] = useState<TabKey>("users");
  if (isPending || !me) return <Skeleton className="h-96" />;

  const allowed = TABS.filter((t) => t.roles.includes(me.role));
  const admin = me.role === "admin";
  const current = allowed.find((t) => t.key === tab) ?? allowed[0];

  return (
    <>
      <PageHeader title="تنظیمات" description="کاربران، تیم‌ها، مراحل فروش، منابع جذب و سوابق ممیزی." />
      {!current ? (
        <Alert>
          <ShieldAlert aria-hidden />
          <AlertTitle>دسترسی به تنظیمات ندارید</AlertTitle>
          <AlertDescription>تنظیمات سامانه با مدیر فروش و ادمین است. برای تغییر با آنها هماهنگ کنید.</AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="flex flex-wrap gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="بخش‌های تنظیمات">
            {allowed.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={current.key === t.key}
                onClick={() => setTab(t.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm",
                  current.key === t.key ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted",
                )}
              >
                <t.icon className="size-4" aria-hidden />
                {t.label}
              </button>
            ))}
          </div>
          <div role="tabpanel">
            {current.key === "users" ? <UsersTab admin={admin} /> : null}
            {current.key === "teams" ? <TeamsTab admin={admin} /> : null}
            {current.key === "stages" ? <StagesTab /> : null}
            {current.key === "sources" ? <SourcesTab /> : null}
            {current.key === "audit" ? <AuditTab /> : null}
          </div>
        </>
      )}
    </>
  );
}
