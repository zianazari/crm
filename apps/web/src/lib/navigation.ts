import {
  ChartColumn,
  Tag,
  Calendar,
  CircleCheckBig,
  House,
  Settings,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

/**
 * Main navigation for release 1 (core sales).
 * Labels follow section 6 of the product spec. Campaigns, automation and
 * tickets are added here when release 2 starts.
 */
export const mainNav: NavItem[] = [
  { href: "/overview", label: "نمای کلی", icon: House },
  { href: "/leads", label: "مشتریان احتمالی", icon: UserPlus },
  { href: "/customers", label: "مشتریان", icon: Users },
  { href: "/deals", label: "فروش‌ها", icon: Tag },
  { href: "/activities", label: "فعالیت‌ها", icon: CircleCheckBig },
  { href: "/calendar", label: "تقویم", icon: Calendar },
  { href: "/reports", label: "گزارش‌ها", icon: ChartColumn },
];

export const secondaryNav: NavItem[] = [
  { href: "/settings", label: "تنظیمات", icon: Settings },
];
