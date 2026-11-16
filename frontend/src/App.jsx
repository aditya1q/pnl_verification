import TopBar from "@/components/layout/TopBar";
import { useHashView, VIEWS } from "@/hooks/useHashView";
import BackofficePage from "@/pages/backoffice/BackofficePage";
import NetPositionPage from "@/pages/net-position/NetPositionPage";

export default function App() {
  const { view, routeKey } = useHashView();
  return (
    // Phones: the page scrolls. From 650px: fills the window and only the tables scroll.
    <div className="flex min-h-dvh flex-col sm:h-dvh sm:overflow-hidden">
      <TopBar view={view} />
      <main className="mx-auto flex w-full max-w-[95%] flex-1 flex-col gap-3 p-3 sm:min-h-0 sm:p-4">
        {view === VIEWS.BACKOFFICE ? <BackofficePage key={routeKey} /> : <NetPositionPage key={routeKey} />}
      </main>
    </div>
  );
}
