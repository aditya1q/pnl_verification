import { useState } from "react";
import { DropdownMenu } from "radix-ui";
import { KeyRound, LogOut, UserPlus, UserRound, Users } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import ToneBadge from "@/components/common/ToneBadge";
import { cn } from "@/lib/utils";
import ChangePasswordDialog from "@/pages/login/ChangePasswordDialog";
import CreateUserDialog from "@/pages/users/CreateUserDialog";
import { ROLE_TONES } from "@/pages/users/roles";

const itemClass = cn(
  "flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none",
  "data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground [&_svg]:size-4 [&_svg]:text-muted-foreground",
);

// User icon on the right of the top bar: account details, password, users (admin) and sign out.
export default function UserMenu() {
  const { user, isAdmin, logout } = useAuth();
  const [dialog, setDialog] = useState(null); // "password" | "create"

  return (
    <>
      <DropdownMenu.Root modal={false}>
        <DropdownMenu.Trigger
          className="grid size-8 place-items-center rounded-full border bg-secondary text-secondary-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent"
          aria-label={`Account: ${user?.username}`} title={user?.username}>
          <UserRound className="size-4" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={6}
            className="z-50 min-w-[210px] rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
            <div className="flex items-center gap-2 px-2 py-2">
              <div className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-xs font-bold uppercase text-primary-foreground">
                {user?.username?.slice(0, 2)}
              </div>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold">{user?.username}</div>
                <ToneBadge tone={ROLE_TONES[user?.role]} className="mt-0.5 capitalize">{user?.role}</ToneBadge>
              </div>
            </div>
            <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border" />
            <DropdownMenu.Item className={itemClass} onSelect={() => setDialog("password")}>
              <KeyRound /> Change password
            </DropdownMenu.Item>
            {isAdmin && (
              <>
                <DropdownMenu.Item className={itemClass} onSelect={() => setDialog("create")}>
                  <UserPlus /> Create user
                </DropdownMenu.Item>
                <DropdownMenu.Item className={itemClass} onSelect={() => { window.location.hash = "#users"; }}>
                  <Users /> Manage users
                </DropdownMenu.Item>
              </>
            )}
            <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-border" />
            <DropdownMenu.Item className={cn(itemClass, "text-destructive [&_svg]:text-destructive")} onSelect={logout}>
              <LogOut /> Sign out
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <ChangePasswordDialog open={dialog === "password"} onClose={() => setDialog(null)} />
      {isAdmin && <CreateUserDialog open={dialog === "create"} onClose={() => setDialog(null)} />}
    </>
  );
}
