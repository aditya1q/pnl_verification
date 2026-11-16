import { useAuth } from "@/auth/AuthProvider";
import Spinner from "@/components/common/Spinner";
import TopBar from "@/components/layout/TopBar";
import { useHashView, VIEWS } from "@/hooks/useHashView";
import BackofficePage from "@/pages/backoffice/BackofficePage";
import LoginPage from "@/pages/login/LoginPage";
import NetPositionPage from "@/pages/net-position/NetPositionPage";
import UsersPage from "@/pages/users/UsersPage";

function Page({ view, routeKey, isAdmin }) {
  if (view === VIEWS.BACKOFFICE) return <BackofficePage key={routeKey} />;
  if (view === VIEWS.USERS && isAdmin) return <UsersPage key={routeKey} />;
  return <NetPositionPage key={routeKey} />;
}

export default function App() {
  const { view, routeKey } = useHashView();
  const { status, isAdmin } = useAuth();
  if (status === "loading") {
    return <div className="grid min-h-dvh place-items-center text-muted-foreground"><Spinner className="size-6" /></div>;
  }
  if (status !== "in") return <LoginPage />;
  return (
    // Phones: the page scrolls. From 650px: fills the window and only the tables scroll.
    <div className="flex min-h-dvh flex-col sm:h-dvh sm:overflow-hidden">
      <TopBar view={view} />
      <main className="mx-auto flex w-full max-w-[95%] flex-1 flex-col gap-3 p-3 sm:min-h-0 sm:p-4">
        <Page view={view} routeKey={routeKey} isAdmin={isAdmin} />
      </main>
    </div>
  );
}
