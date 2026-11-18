import {
  ChartColumn,
  Tag,
  Calendar,
  CircleCheckBig,
  House,
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
};

/**
 * Main navigation for release 1 (core sales).
 * Labels follow section 6 of the product spec. Campaigns and tickets are added
 * here when they are built.
 */
export const mainNav: NavItem[] = [
  { href: "/overview", label: "نمای کلی", icon: House },
  { href: "/leads", label: "مشتریان احتمالی", icon: UserPlus },
  { href: "/customers", label: "مشتریان", icon: Users },
  { href: "/deals", label: "فروش‌ها", icon: Tag },
  { href: "/activities", label: "فعالیت‌ها", icon: CircleCheckBig },
  { href: "/calendar", label: "تقویم", icon: Calendar },
  { href: "/reports", label: "گزارش‌ها", icon: ChartColumn },
  { href: "/automations", label: "اتوماسیون", icon: Workflow, managersOnly: true },
];

export const secondaryNav: NavItem[] = [
  { href: "/settings", label: "تنظیمات", icon: Settings },
];
