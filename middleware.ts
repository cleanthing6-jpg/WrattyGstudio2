import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const publicRoutes = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/setup",
]);

export default clerkMiddleware(async (auth, request) => {
  if (!publicRoutes.isPublic(request.url)) {
    await auth();
  }
});

export const config = { matcher: ["/((?!_next|[^?]*\\.(?:html?|css|js|jpg|png|svg|ico|woff|woff2|ttf|eot)).*)"] };
