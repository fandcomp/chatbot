import { MemberList } from "@/components/organizations/member-list";

export default function UsersPage() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-6 py-12">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground">
          Manage who has access to this organization and what they can do.
        </p>
      </div>
      <MemberList />
    </div>
  );
}
