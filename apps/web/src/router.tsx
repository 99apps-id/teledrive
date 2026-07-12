import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { App } from "./App";

const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

const driveRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: App,
});

const routeTree = rootRoute.addChildren([driveRoute]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  defaultPreloadStaleTime: 5_000,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
