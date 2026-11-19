import {
  ChartColumn,
  Tag,
  Calendar,
  CircleCheckBig,
  House,
  Inbox,
  LifeBuoy,
  Megaphone,
  Settings,
  UserPlus,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown only to sales managers and admins (the API enforces the same). */
  managersOnly?: boolean;
  /** Sales views, which finance team members do not get (spec section 5). */
  sales?: boolean;
  /** Shown to users who can open a team queue. */
  queue?: boolean;
};

/**
 * Main navigation for release 1 (core sales).
 * Labels follow section 6 of the product spec. Campaigns and tickets are added
 * here when they are built.
 */
export const mainNav: NavItem[] = [
  { href: "/overview", label: "نمای کلی", icon: House, sales: true },
  { href: "/leads", label: "مشتریان احتمالی", icon: UserPlus, sales: true },
  { href: "/customers", label: "مشتریان", icon: Users, sales: true },
  { href: "/deals", label: "فروش‌ها", icon: Tag, sales: true },
  { href: "/activities", label: "فعالیت‌ها", icon: CircleCheckBig },
  { href: "/team-queue", label: "صف کار تیم", icon: Inbox, queue: true },
  { href: "/tickets", label: "تیکت‌ها", icon: LifeBuoy, sales: true },
  { href: "/calendar", label: "تقویم", icon: Calendar },
  { href: "/reports", label: "گزارش‌ها", icon: ChartColumn, sales: true },
  { href: "/campaigns", label: "کمپین‌ها", icon: Megaphone, managersOnly: true, sales: true },
  { href: "/automations", label: "اتوماسیون", icon: Workflow, managersOnly: true },
];

export const secondaryNav: NavItem[] = [
  { href: "/settings", label: "تنظیمات", icon: Settings },
];
