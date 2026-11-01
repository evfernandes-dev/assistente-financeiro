import { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export type TestSql = (
  strings: TemplateStringsArray,
  ...values: unknown[]
) => Promise<unknown[]>;

export interface TestDatabase {
  db: PGlite;
  sql: TestSql;
}

export async function createTestDatabase(): Promise<TestDatabase> {
  const db = new PGlite();
  const schemaPath = fileURLToPath(
    new URL("../../../database/schema.sql", import.meta.url),
  );
  const schema = readFileSync(schemaPath, "utf8");

  await db.exec(schema);

  const sql: TestSql = async (strings, ...values) => {
    let text = "";
    strings.forEach((part, index) => {
      text += part;
      if (index < values.length) {
        text += `$${index + 1}`;
      }
    });

    const result = await db.query(text, values);
    return result.rows;
  };

  return { db, sql };
}

export async function resetTestDatabase(db: PGlite): Promise<void> {
  await db.exec(
    "truncate table audit_log, transactions, categories, users restart identity cascade;",
  );
}
