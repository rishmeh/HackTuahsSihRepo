/* Editorial Study Desk: route-level shell stays quiet and lets the focused workspace carry the hierarchy. */
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { trpc } from "@/lib/trpc";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import { DashboardLayoutSkeleton } from "./components/DashboardLayoutSkeleton";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";

function Gate() {
  const me = trpc.profile.me.useQuery();
  // A student's first stop after enrolling is the onboarding story. Parents
  // never see it, and if the ml service is down the desk still opens.
  const onboarding = trpc.onboarding.status.useQuery(undefined, {
    enabled: !!me.data && me.data.role === "student",
    retry: 1,
    refetchOnWindowFocus: false,
  });

  if (me.isLoading) return <DashboardLayoutSkeleton />;
  if (!me.data) return <Login onLoggedIn={() => me.refetch()} />;

  if (me.data.role === "student") {
    if (onboarding.isLoading) return <DashboardLayoutSkeleton />;
    if (onboarding.data && !onboarding.data.completed) {
      return <Onboarding profile={me.data} onDone={() => onboarding.refetch()} />;
    }
  }

  return <Home profile={me.data} onLoggedOut={() => me.refetch()} />;
}

function Router() {
  return (
    <Switch>
      <Route path="/" component={Gate} />
      <Route path="/404" component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
