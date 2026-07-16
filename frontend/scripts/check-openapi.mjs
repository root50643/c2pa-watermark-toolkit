import { execFileSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const target = new URL("../src/generated/api.d.ts", import.meta.url);
const temporary = join(tmpdir(), `raiw-openapi-${process.pid}.d.ts`);

try {
  const cli = fileURLToPath(new URL("../node_modules/openapi-typescript/bin/cli.js", import.meta.url));
  execFileSync(process.execPath, [cli, "../openapi/openapi.json", "-o", temporary], {
    cwd: new URL("..", import.meta.url),
    stdio: "ignore"
  });
  if (readFileSync(target, "utf8") !== readFileSync(temporary, "utf8")) {
    throw new Error("Generated API types are out of date. Run pnpm generate:api.");
  }
} finally {
  rmSync(temporary, { force: true });
}
