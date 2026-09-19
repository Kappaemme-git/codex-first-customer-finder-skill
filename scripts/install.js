#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");

function usage() {
  console.log(`
Codex First Customer Finder Skill installer

Usage:
  npx codex-first-customer-finder-skill
  codex-first-customer-finder-skill --skills-dir ~/.codex/skills

Options:
  --skills-dir PATH  Install into a custom Codex skills directory
  --help             Show this help
`);
}

function expandHome(value) {
  if (!value) return value;
  if (value === "~") return os.homedir();
  if (value.startsWith("~/")) return path.join(os.homedir(), value.slice(2));
  return value;
}

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
      continue;
    }
    if (arg === "--skills-dir") {
      const value = argv[index + 1];
      if (!value) throw new Error("--skills-dir requires a value");
      options.skillsDir = expandHome(value);
      index += 1;
      continue;
    }
    throw new Error(`Unknown option: ${arg}`);
  }
  return options;
}

function defaultSkillsDir() {
  const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
  return path.join(codexHome, "skills");
}

function copyDirectory(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (entry.name === "__pycache__" || entry.name.endsWith(".pyc")) continue;
    const sourcePath = path.join(source, entry.name);
    const destinationPath = path.join(destination, entry.name);
    if (entry.isDirectory()) copyDirectory(sourcePath, destinationPath);
    else if (entry.isFile()) fs.copyFileSync(sourcePath, destinationPath);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    usage();
    return;
  }

  const source = path.resolve(__dirname, "..", "first-customer-finder");
  const skillsDir = path.resolve(options.skillsDir || defaultSkillsDir());
  const destination = path.join(skillsDir, "first-customer-finder");
  if (!fs.existsSync(source)) throw new Error(`Cannot find bundled skill at ${source}`);

  fs.mkdirSync(skillsDir, { recursive: true });
  let destinationStat;
  try { destinationStat = fs.lstatSync(destination); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  if (destinationStat && destinationStat.isSymbolicLink()) {
    throw new Error("The installed skill is a symlink; update its source explicitly instead.");
  }
  // Stage first and keep the previous installation recoverable.
  const stagingRoot = fs.mkdtempSync(path.join(skillsDir, ".first-customer-finder-stage-"));
  const staged = path.join(stagingRoot, "first-customer-finder");
  copyDirectory(source, staged);
  let backup;
  if (fs.existsSync(destination)) {
    const backupRoot = path.join(path.dirname(skillsDir), "skill-backups");
    fs.mkdirSync(backupRoot, { recursive: true });
    backup = path.join(fs.mkdtempSync(path.join(backupRoot, "first-customer-finder-")), "first-customer-finder");
    fs.renameSync(destination, backup);
  }
  try {
    fs.renameSync(staged, destination);
    fs.rmdirSync(stagingRoot);
  } catch (error) {
    if (backup && !fs.existsSync(destination)) fs.renameSync(backup, destination);
    throw error;
  }

  console.log("Installed first-customer-finder skill.");
  console.log(`Location: ${destination}`);
  if (backup) console.log(`Previous installation preserved at: ${backup}`);
  console.log("");
  console.log("Restart Codex, then run:");
  console.log("  Use $first-customer-finder to find ten potential first customers for https://example.com.");
}

try {
  main();
} catch (error) {
  console.error(`Error: ${error.message}`);
  process.exit(1);
}
