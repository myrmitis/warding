/**
 * The ten chat channels and their honest approval capability.
 * Five have in-chat Approve / Deny buttons, WhatsApp takes a typed reply,
 * four are chat-only (approvals planned, not built; see backlog #16).
 */
export type ApprovalMode = "buttons" | "typed" | "chat-only";

export interface Channel {
  slug: string;
  name: string;
  approval: ApprovalMode;
  /** What is planned for chat-only channels; empty when nothing is scheduled. */
  planned: "" | "buttons" | "typed";
}

export const APPROVAL_LABEL: Record<ApprovalMode, string> = {
  buttons: "Buttons",
  typed: "Typed reply",
  "chat-only": "Chat only",
};

export const channels: Channel[] = [
  { slug: "slack", name: "Slack", approval: "buttons", planned: "" },
  { slug: "discord", name: "Discord", approval: "buttons", planned: "" },
  { slug: "telegram", name: "Telegram", approval: "buttons", planned: "" },
  { slug: "teams", name: "Teams", approval: "buttons", planned: "" },
  { slug: "webex", name: "Webex", approval: "buttons", planned: "" },
  { slug: "whatsapp", name: "WhatsApp", approval: "typed", planned: "" },
  { slug: "imessage", name: "iMessage", approval: "chat-only", planned: "typed" },
  { slug: "wechat", name: "WeChat", approval: "chat-only", planned: "" },
  { slug: "wecom", name: "WeCom", approval: "chat-only", planned: "buttons" },
  { slug: "feishu", name: "Feishu", approval: "chat-only", planned: "buttons" },
];

export const channelCounts = {
  buttons: channels.filter((c) => c.approval === "buttons").length,
  typed: channels.filter((c) => c.approval === "typed").length,
  chatOnly: channels.filter((c) => c.approval === "chat-only").length,
  total: channels.length,
};
