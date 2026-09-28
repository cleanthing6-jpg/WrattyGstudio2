import { neon } from "@neondatabase/serverless";

type Sql = ReturnType<typeof neon<false, false>>;

let client: Sql | undefined;

function getClient(): Sql {
  if (!client) client = neon(process.env.DATABASE_URL!);
  return client;
}

export const sql: Sql = new Proxy(
  (function () {}) as unknown as Sql,
  {
    apply(_target, thisArg, args) {
      return Reflect.apply(
        getClient() as unknown as (...a: unknown[]) => unknown,
        thisArg,
        args,
      );
    },
    get(_target, prop) {
      const value = Reflect.get(getClient() as unknown as object, prop);
      return typeof value === "function"
        ? (value as (...a: unknown[]) => unknown).bind(getClient())
        : value;
    },
  },
) as Sql;
