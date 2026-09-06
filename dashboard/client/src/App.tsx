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

function Gate() {
  const me = trpc.profile.me.useQuery();

  if (me.isLoading) return <DashboardLayoutSkeleton />;
  if (!me.data) return <Login onLoggedIn={() => me.refetch()} />;
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
