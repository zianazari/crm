import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { DuplicateMatch } from "@/lib/types";

const KIND_LABELS = { customer: "مشتری", lead: "مشتری احتمالی" } as const;
const FIELD_LABELS = { mobile: "موبایل", email: "ایمیل" } as const;

export function DuplicateAlert({ matches }: { matches: DuplicateMatch[] }) {
  return (
    <Alert className="border-warning-foreground/30 bg-warning text-warning-foreground">
      <TriangleAlert aria-hidden />
      <AlertTitle>پرونده مشابه وجود دارد</AlertTitle>
      <AlertDescription className="text-warning-foreground/90">
        <ul className="mt-1 space-y-1">
          {matches.map((m) => (
            <li key={`${m.kind}-${m.id}`}>
              {m.access === "full" ? (
                <Link
                  href={m.kind === "customer" ? `/customers/${m.id}` : `/leads/${m.id}`}
                  className="font-medium underline underline-offset-4"
                >
                  {m.full_name}
                </Link>
              ) : (
                <span className="font-medium">{m.full_name}</span>
              )}{" "}
              ({KIND_LABELS[m.kind]}، هم‌{m.matched_on.map((f) => FIELD_LABELS[f]).join(" و ")}، مسئول:{" "}
              {m.owner.full_name})
            </li>
          ))}
        </ul>
        <p className="mt-2">
          اگر همان شخص است، به جای ساخت پرونده تازه از پرونده موجود استفاده کنید یا با مسئول آن هماهنگ
          شوید.
        </p>
      </AlertDescription>
    </Alert>
  );
}
