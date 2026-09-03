import { clerkMiddleware } from "@clerk/nextjs/server";
export default clerkMiddleware();
export const config = { matcher: ["/((?!_next|[^?]*\\.(?:html?|css|js|jpg|png|svg|ico)).*)", "/api(.*)"] };
