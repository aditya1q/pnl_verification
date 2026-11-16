import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const ROLES = [
  { value: "admin", label: "Admin", hint: "Everything, plus managing users" },
  { value: "operator", label: "Operator", hint: "View, imports and LTP changes" },
  { value: "viewer", label: "Viewer", hint: "View only" },
];

export const ROLE_TONES = { admin: "cf", operator: "close", viewer: "neutral" };

// Fired after a user is added, so an open Users page reloads its list.
export const USERS_CHANGED = "users-changed";

export function RoleSelect({ value, onChange, disabled, id, className = "w-[120px]" }) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} size="sm" className={className} aria-label="Role"><SelectValue /></SelectTrigger>
      <SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
    </Select>
  );
}
