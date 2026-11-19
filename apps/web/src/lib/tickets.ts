/** Tickets in the staff panel (spec 4.9). */

import type { TicketStatus } from "@/lib/portal";
import type { UserRef } from "@/lib/types";

export type Ticket = {
  id: string;
  number: number;
  subject: string;
  status: TicketStatus;
  customer: { id: string; full_name: string };
  assignee: UserRef | null;
  opened_by_user: UserRef | null;
  opened_by_customer: boolean;
  created_at: string;
  last_message_at: string;
  closed_at: string | null;
  version: number;
  can_manage: boolean;
};

export type TicketMessage = {
  id: string;
  body: string;
  internal: boolean;
  author: string;
  from_customer: boolean;
  created_at: string;
};

export type TicketDetail = Ticket & { messages: TicketMessage[] };

export type PortalAccess = {
  id: string;
  channel: "sms" | "email";
  address: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};
