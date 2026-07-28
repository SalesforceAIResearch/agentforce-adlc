import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const toolchainConfig = JSON.parse(
  fs.readFileSync(
    path.join(scriptDirectory, "agentscript-toolchain.json"),
    "utf8",
  ),
);
const assetRoot = path.resolve(
  process.argv[2] ?? "skills/agentforce-generate/assets",
);
const temporaryRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), "agentforce-agentscript-"),
);
const checkout = path.join(temporaryRoot, "agentscript");
const sourceRef = process.env.AGENTSCRIPT_REF ?? toolchainConfig.ref;

function run(command, args, cwd, capture = false) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    env: process.env,
    stdio: capture ? "pipe" : "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (capture && result.stderr) process.stderr.write(result.stderr);
    throw new Error(`${command} exited with status ${result.status}`);
  }
  return capture ? result.stdout.trim() : "";
}

let exitCode = 1;
try {
  fs.mkdirSync(checkout);
  run("git", ["init", "--quiet"], checkout);
  run("git", ["remote", "add", "origin", toolchainConfig.repository], checkout);
  run("git", ["fetch", "--depth", "1", "origin", sourceRef], checkout);
  run("git", ["checkout", "--quiet", "--detach", "FETCH_HEAD"], checkout);
  const commit = run("git", ["rev-parse", "HEAD"], checkout, true);
  run("corepack", ["pnpm", "install", "--frozen-lockfile"], checkout);
  // Keep this explicit pure-JS dependency chain. A broad filtered workspace
  // build currently reaches optional tree-sitter prebuilds that require
  // platform toolchains and network-fetched Node headers.
  for (const packageName of toolchainConfig.sourceBuildPackages) {
    run("corepack", ["pnpm", "--filter", packageName, "build"], checkout);
  }

  const sdkManifest = JSON.parse(
    fs.readFileSync(
      path.join(checkout, "packages", "agentforce", "package.json"),
      "utf8",
    ),
  );
  if (sdkManifest.name !== toolchainConfig.sourcePackage) {
    throw new Error(
      `Expected source package ${toolchainConfig.sourcePackage}, found ` +
        `${sdkManifest.name}.`,
    );
  }
  console.error(
    `Validating with ${sdkManifest.name} ${sdkManifest.version} from ` +
      `${toolchainConfig.repository} at ${commit}.`,
  );

  const validation = spawnSync(
    process.execPath,
    [path.join(scriptDirectory, "validate_agent_assets.mjs"), assetRoot],
    {
      env: {
        ...process.env,
        AGENTSCRIPT_SDK: path.join(
          checkout,
          "packages",
          "agentforce",
          "dist",
          "index.js",
        ),
        AGENTSCRIPT_SOURCE_BUILD: "1",
      },
      stdio: "inherit",
    },
  );
  if (validation.error) throw validation.error;
  exitCode = validation.status ?? 1;
} catch (error) {
  console.error(
    `Unable to validate with open-source AgentScript: ${error.message}`,
  );
} finally {
  if (process.env.KEEP_AGENTSCRIPT_CHECKOUT === "1") {
    console.error(`Kept AgentScript checkout at ${checkout}.`);
  } else {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

process.exit(exitCode);
