import type { OgPage } from "../og-pages";

/** OG cards for the trust pages: security, approvals, privacy, terms. */
export const pages: OgPage[] = [
  { slug: "security", h1: "Some things it is not allowed to do.", qualifier: "Keystone paths · deny rules · redaction · chained log · per-OS scope", register: "paper" },
  { slug: "approvals", h1: "Approve before, not after.", qualifier: "Five chat apps with buttons · WhatsApp typed · four chat-only", register: "paper" },
  { slug: "privacy", h1: "Privacy", qualifier: "A plain-language summary: what this site and the product send, and to whom", register: "paper" },
  { slug: "terms", h1: "Terms", qualifier: "A plain-language summary: licence, refunds, and what is not promised", register: "paper" },
];
