import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const toolchainConfig = JSON.parse(
  fs.readFileSync(
    new URL("./agentscript-toolchain.json", import.meta.url),
    "utf8",
  ),
);
const assetRoot = path.resolve(
  process.argv[2] ?? "skills/agentforce-generate/assets",
);
const parserPath = process.env.AGENTSCRIPT_PARSER;
if (!parserPath) {
  console.error(
    "Set AGENTSCRIPT_PARSER to a current AgentScript SDK entry point, or run " +
      "`node tests/validate_agent_assets_from_source.mjs` to build the open-source SDK.",
  );
  process.exit(2);
}
const resolvedParserPath = path.resolve(parserPath);

function sdkMetadata(entryPoint) {
  let directory = path.dirname(fs.realpathSync(entryPoint));
  while (true) {
    const manifestPath = path.join(directory, "package.json");
    if (fs.existsSync(manifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
      if (toolchainConfig.packages.includes(manifest.name)) {
        return { name: manifest.name, version: manifest.version };
      }
    }
    const parent = path.dirname(directory);
    if (parent === directory) return null;
    directory = parent;
  }
}

function versionParts(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(version);
  if (!match) throw new Error(`Unsupported SDK version format: ${version}`);
  return match.slice(1).map(Number);
}

function compareVersions(left, right) {
  const leftParts = versionParts(left);
  const rightParts = versionParts(right);
  for (let index = 0; index < leftParts.length; index += 1) {
    if (leftParts[index] !== rightParts[index]) {
      return leftParts[index] - rightParts[index];
    }
  }
  return 0;
}

let sdk;
try {
  sdk = sdkMetadata(resolvedParserPath);
} catch (error) {
  console.error(`Unable to inspect AGENTSCRIPT_PARSER: ${error.message}`);
  process.exit(2);
}
if (!sdk) {
  console.error(
    "AGENTSCRIPT_PARSER must resolve inside a supported AgentScript SDK package: " +
      `${toolchainConfig.packages.join(" or ")}.`,
  );
  process.exit(2);
}
if (compareVersions(sdk.version, toolchainConfig.minimumVersion) < 0) {
  console.error(
    `${sdk.name} ${sdk.version} is stale; this repository requires ` +
      `${toolchainConfig.minimumVersion} or newer. Build the current open-source SDK with ` +
      "`node tests/validate_agent_assets_from_source.mjs`.",
  );
  process.exit(2);
}

const parserModule = pathToFileURL(resolvedParserPath).href;

let compileSource;
try {
  ({ compileSource } = await import(parserModule));
} catch (error) {
  console.error(
    `Unable to import the AgentScript SDK from AGENTSCRIPT_PARSER: ${error.message}`,
  );
  process.exit(2);
}

function agentFiles(directory) {
  return fs
    .readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) return agentFiles(entryPath);
      return entry.isFile() && entry.name.endsWith(".agent") ? [entryPath] : [];
    })
    .sort();
}

const failures = [];
const diagnosticCounts = new Map();
for (const file of agentFiles(assetRoot)) {
  const result = compileSource(fs.readFileSync(file, "utf8"));
  for (const diagnostic of result.diagnostics) {
    const key = `${diagnostic.severity}:${diagnostic.code}`;
    diagnosticCounts.set(key, (diagnosticCounts.get(key) ?? 0) + 1);
  }
  const blockingDiagnostics = result.diagnostics
    .filter((diagnostic) => diagnostic.severity <= 2)
    .map((diagnostic) => ({
      line: diagnostic.range.start.line + 1,
      severity: diagnostic.severity === 1 ? "error" : "warning",
      code: diagnostic.code,
      message: diagnostic.message,
    }));
  if (blockingDiagnostics.length > 0) {
    failures.push({ file, diagnostics: blockingDiagnostics });
  }
}

console.log(
  JSON.stringify(
    {
      assetRoot,
      toolchain: sdk,
      minimumVersion: toolchainConfig.minimumVersion,
      validation: "parse+lint+compile (errors and warnings)",
      files: agentFiles(assetRoot).length,
      diagnostics: Object.fromEntries(
        [...diagnosticCounts.entries()].sort(([left], [right]) =>
          left.localeCompare(right),
        ),
      ),
      failures,
    },
    null,
    2,
  ),
);
process.exit(failures.length === 0 ? 0 : 1);
