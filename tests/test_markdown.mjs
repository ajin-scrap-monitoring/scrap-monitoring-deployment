import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { collectMarkdownFiles, lintMarkdown } from "../tools/lint-markdown.mjs";

const runner = fileURLToPath(new URL("../tools/lint-markdown.mjs", import.meta.url));

async function fixture(t) {
  const directory = await mkdtemp(join(tmpdir(), "scrap-markdown-test-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await writeFile(join(directory, ".markdownlint.json"), '{"MD013":false}\n');
  return directory;
}

async function document(root, path, content = "# Example\n") {
  const destination = join(root, path);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, content);
}

test("collects root, nested and hidden Markdown files in stable order", async (t) => {
  const root = await fixture(t);
  for (const path of ["docs/z.md", "README.md", ".agents/AGENTS.md", "docs/a.md"]) {
    await document(root, path);
  }
  await document(root, "docs/notes.txt");
  assert.deepEqual(await collectMarkdownFiles(root), [
    ".agents/AGENTS.md",
    "README.md",
    "docs/a.md",
    "docs/z.md",
  ]);
});

test("excludes Git data and dependency directories at every depth", async (t) => {
  const root = await fixture(t);
  await document(root, "README.md");
  for (const directory of [".git", ".venv", "node_modules", "nested/node_modules"]) {
    await document(root, `${directory}/invalid.md`, "not a heading\n");
  }
  assert.deepEqual(await collectMarkdownFiles(root), ["README.md"]);
  assert.deepEqual((await lintMarkdown(root)).diagnostics, []);
});

test("validates internal Markdown file symbolic links without traversing directory links", async (t) => {
  const root = await fixture(t);
  await document(root, ".agents/AGENTS.md");
  await symlink(".agents/AGENTS.md", join(root, "AGENTS.md"));
  await symlink(".", join(root, "directory-loop"));
  assert.deepEqual(await collectMarkdownFiles(root), [".agents/AGENTS.md", "AGENTS.md"]);
  assert.deepEqual((await lintMarkdown(root)).diagnostics, []);
});

test("rejects Markdown symbolic links outside the repository", async (t) => {
  const root = await fixture(t);
  const outside = await fixture(t);
  await document(outside, "external.md");
  await symlink(join(outside, "external.md"), join(root, "external.md"));
  await assert.rejects(collectMarkdownFiles(root), /leaves the repository/);
});

test("rejects missing Markdown symbolic link targets", async (t) => {
  const root = await fixture(t);
  await symlink("missing.md", join(root, "broken.md"));
  await assert.rejects(collectMarkdownFiles(root), { code: "ENOENT" });
});

test("rejects Markdown symbolic links to directories", async (t) => {
  const root = await fixture(t);
  await mkdir(join(root, "docs"));
  await symlink("docs", join(root, "directory.md"));
  await assert.rejects(collectMarkdownFiles(root), /not a regular file/);
});

test("keeps the configured line length exception and other Markdown rules", async (t) => {
  const root = await fixture(t);
  await document(root, "valid.md", `# Example\n\n${"a".repeat(120)}\n`);
  await document(root, "invalid.md", "# Example\n\n##Skipped\n");
  const { diagnostics } = await lintMarkdown(root);
  assert(diagnostics.some((message) => (
    message.startsWith("invalid.md:3:") && message.includes("MD018")
  )));
  assert(diagnostics.every((message) => !message.startsWith("valid.md:")));
});

test("rejects an empty Markdown input set", async (t) => {
  const root = await fixture(t);
  await assert.rejects(lintMarkdown(root), /No Markdown files found/);
});

test("does not fall back when configuration is missing, malformed or not an object", async (t) => {
  const root = await fixture(t);
  await document(root, "README.md");
  const config = join(root, ".markdownlint.json");
  await rm(config);
  await assert.rejects(lintMarkdown(root));
  for (const value of ["{", "null", "[]", '"invalid"']) {
    await writeFile(config, value);
    await assert.rejects(lintMarkdown(root));
  }
});

test("command exits successfully for valid Markdown", async (t) => {
  const root = await fixture(t);
  await document(root, "README.md");
  const result = spawnSync(process.execPath, [runner], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Markdown: 1 files, 0 errors/);
});

test("command reports rule and path and fails for invalid Markdown", async (t) => {
  const root = await fixture(t);
  await document(root, "README.md", "# Example\n\n##Skipped\n");
  const result = spawnSync(process.execPath, [runner], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /README\.md:3:\d+ MD018/);
});

test("command fails for unexpected arguments and missing configuration", async (t) => {
  const root = await fixture(t);
  const unexpected = spawnSync(process.execPath, [runner, "--unknown"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(unexpected.status, 1);
  assert.match(unexpected.stderr, /Usage:/);
  await rm(join(root, ".markdownlint.json"));
  const missing = spawnSync(process.execPath, [runner], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /Markdown validation failed/);
});
