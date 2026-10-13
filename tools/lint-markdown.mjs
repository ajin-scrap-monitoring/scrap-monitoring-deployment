import { readFile, readdir, realpath, stat } from "node:fs/promises";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { lint } from "markdownlint/promise";

const ignoredDirectories = new Set([".git", ".venv", "node_modules"]);

export async function collectMarkdownFiles(rootDirectory) {
  const root = await realpath(rootDirectory);
  const files = [];

  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!ignoredDirectories.has(entry.name)) {
          await visit(path);
        }
      } else if (entry.name.endsWith(".md")) {
        if (entry.isSymbolicLink()) {
          const target = await realpath(path);
          const targetPath = relative(root, target);
          if (
            isAbsolute(targetPath) ||
            targetPath === ".." ||
            targetPath.startsWith(`..${sep}`)
          ) {
            throw new Error(
              `Markdown symbolic link leaves the repository: ${relative(root, path)}`,
            );
          }
          if (!(await stat(target)).isFile()) {
            throw new Error(
              `Markdown symbolic link is not a regular file: ${relative(root, path)}`,
            );
          }
        } else if (!entry.isFile()) {
          throw new Error(`Markdown path is not a regular file: ${relative(root, path)}`);
        }
        files.push(relative(root, path));
      }
    }
  }

  await visit(root);
  return files.sort();
}

export async function lintMarkdown(rootDirectory) {
  const root = await realpath(rootDirectory);
  const config = JSON.parse(await readFile(join(root, ".markdownlint.json"), "utf8"));
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    throw new Error("Markdown configuration must be a JSON object.");
  }
  const files = await collectMarkdownFiles(root);
  if (files.length === 0) {
    throw new Error("No Markdown files found.");
  }
  const results = await lint({ files: files.map((file) => join(root, file)), config });
  const diagnostics = [];
  for (const file of files) {
    for (const error of results[join(root, file)]) {
      const column = error.errorRange?.[0] ?? 1;
      const detail = error.errorDetail ? ` [${error.errorDetail}]` : "";
      diagnostics.push(
        `${file}:${error.lineNumber}:${column} ${error.ruleNames.join("/")} ${error.ruleDescription}${detail}`,
      );
    }
  }
  return { files, diagnostics };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    if (process.argv.length !== 2) {
      throw new Error("Usage: node tools/lint-markdown.mjs");
    }
    const { files, diagnostics } = await lintMarkdown(process.cwd());
    for (const diagnostic of diagnostics) {
      console.error(diagnostic);
    }
    console.log(`Markdown: ${files.length} files, ${diagnostics.length} errors.`);
    process.exitCode = diagnostics.length > 0 ? 1 : 0;
  } catch (error) {
    console.error(`Markdown validation failed: ${error.message}`);
    process.exitCode = 1;
  }
}
