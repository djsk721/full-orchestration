import type { Role } from "./configuration";

export interface ToolRule {
  access: "read" | "write";
  roles?: readonly Role[];
  agents?: readonly string[];
  native?: boolean;
}

export interface ToolContext {
  role?: Role;
  agent?: string;
  native?: boolean;
  selected?: boolean;
}

export function toolDecision(rule: ToolRule | undefined, context: ToolContext): "deny" | "read" | "approval-required" {
  if (!rule || (rule.access !== "read" && rule.access !== "write") || context.selected === false) return "deny";
  if (rule.agents?.length && (!context.agent || !rule.agents.includes(context.agent))) return "deny";
  if (context.native) {
    return rule.access === "read" && rule.native === true && !rule.agents?.length ? "read" : "deny";
  }
  if (!context.role || !rule.roles?.includes(context.role)) return "deny";
  return rule.access === "read" ? "read" : context.role === "developer" ? "approval-required" : "deny";
}

/** Reconcile observations without invoking a tool. Only a fresh, approved write can proceed. */
export function writeDisposition(approval: "missing" | "approved" | "denied", journal: "missing" | "started" | "done"):
  "await-approval" | "deny" | "stop-uncertain" | "reuse-result" | "start" {
  if (approval !== "approved") return approval === "missing" ? "await-approval" : "deny";
  if (journal === "started") return "stop-uncertain";
  return journal === "done" ? "reuse-result" : "start";
}
