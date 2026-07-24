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

function packageEntryPoint(packageName) {
  for (const binDirectory of (process.env.PATH ?? "").split(path.delimiter)) {
    if (path.basename(binDirectory) !== ".bin") continue;
    const packageDirectory = path.join(
      path.dirname(binDirectory),
      ...packageName.split("/"),
    );
    const manifestPath = path.join(packageDirectory, "package.json");
    if (!fs.existsSync(manifestPath)) continue;
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    return path.join(packageDirectory, manifest.main ?? "dist/index.js");
  }
  return null;
}

const sourceBuild = process.env.AGENTSCRIPT_SOURCE_BUILD === "1";
const expectedPackage = sourceBuild
  ? toolchainConfig.sourcePackage
  : toolchainConfig.publishedPackage;
const sdkPath =
  process.env.AGENTSCRIPT_SDK ?? packageEntryPoint(expectedPackage);
if (!sdkPath) {
  console.error(
    "Run this validator with the supported public SDK:\n" +
      `  npx --yes --package=${toolchainConfig.publishedPackage}` +
      `@${toolchainConfig.minimumVersion} -- ` +
      "node tests/validate_agent_assets.mjs\n" +
      "If that package is unavailable or stale, run " +
      "`node tests/validate_agent_assets_from_source.mjs`.",
  );
  process.exit(2);
}
const resolvedSdkPath = path.resolve(sdkPath);

function sdkMetadata(entryPoint) {
  let directory = path.dirname(fs.realpathSync(entryPoint));
  while (true) {
    const manifestPath = path.join(directory, "package.json");
    if (fs.existsSync(manifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
      if (manifest.name === expectedPackage) {
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
  sdk = sdkMetadata(resolvedSdkPath);
} catch (error) {
  console.error(`Unable to inspect AgentScript SDK: ${error.message}`);
  process.exit(2);
}
if (!sdk) {
  console.error(
    `AgentScript SDK entry point must resolve inside ${expectedPackage}.`,
  );
  process.exit(2);
}
if (compareVersions(sdk.version, toolchainConfig.minimumVersion) < 0) {
  console.error(
    `${sdk.name} ${sdk.version} is stale; this repository requires ` +
      `${toolchainConfig.minimumVersion} or newer. Build the pinned open-source SDK with ` +
      "`node tests/validate_agent_assets_from_source.mjs`.",
  );
  process.exit(2);
}

const sdkModule = pathToFileURL(resolvedSdkPath).href;

let compileSource;
try {
  ({ compileSource } = await import(sdkModule));
} catch (error) {
  console.error(
    `Unable to import the AgentScript SDK: ${error.message}`,
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
const files = agentFiles(assetRoot);
if (files.length === 0) {
  console.error(`No .agent files found under ${assetRoot}.`);
  process.exit(2);
}

const requiredArtifactKeys = [
  "schema_version",
  "global_configuration",
  "agent_version",
];

let negativeControl = "passed";
function failNegativeControl(message) {
  negativeControl = "failed";
  failures.push({
    file: "<negative-control>",
    diagnostics: [],
    artifactIssues: [message],
  });
}

try {
  const invalidResult = compileSource("this is not valid AgentScript\n");
  if (!invalidResult || !Array.isArray(invalidResult.diagnostics)) {
    failNegativeControl(
      "The SDK returned an invalid result for deliberately malformed AgentScript.",
    );
  } else if (
    !invalidResult.diagnostics.some((diagnostic) => diagnostic.severity <= 2)
  ) {
    failNegativeControl(
      "The SDK accepted deliberately malformed AgentScript.",
    );
  }
} catch (error) {
  failNegativeControl(
    `The SDK threw instead of returning diagnostics: ${error.message}`,
  );
}

for (const file of files) {
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
  const artifactIssues = [];
  if (!result.output || typeof result.output !== "object") {
    artifactIssues.push("Compiler did not emit an output object.");
  } else {
    for (const key of requiredArtifactKeys) {
      if (
        !Object.prototype.hasOwnProperty.call(result.output, key) ||
        result.output[key] === null ||
        result.output[key] === undefined
      ) {
        artifactIssues.push(`Emitted output is missing required field '${key}'.`);
      }
    }
  }
  if (blockingDiagnostics.length > 0 || artifactIssues.length > 0) {
    failures.push({
      file,
      diagnostics: blockingDiagnostics,
      artifactIssues,
    });
  }
}

console.log(
  JSON.stringify(
    {
      assetRoot,
      toolchain: sdk,
      minimumVersion: toolchainConfig.minimumVersion,
      validation:
        "parse+lint+compile+emitted-artifact (errors and warnings)",
      negativeControl,
      files: files.length,
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
