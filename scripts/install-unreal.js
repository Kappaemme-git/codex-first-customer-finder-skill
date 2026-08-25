#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");

const SKILLS = {
  original: "first-customer-finder",
  umg: "unreal-media-brand-prospector",
  talent: "unreal-talent-campaign-prospector",
};

function usage() {
  console.log(`
Unreal Prospecting Skills installer

Usage:
  unreal-prospecting-skills --skill umg
  unreal-prospecting-skills --skill talent
  unreal-prospecting-skills --skill unreal
  unreal-prospecting-skills --skill all
  unreal-prospecting-skills --skill original

Options:
  --skill NAME       original, umg, talent, unreal (both Unreal skills), or all
  --skills-dir PATH  Install into a custom Codex skills directory
  --help             Show this help
`);
}

function expandHome(value) {
  if (value === "~") return os.homedir();
  if (value && value.startsWith("~/")) return path.join(os.homedir(), value.slice(2));
  return value;
}

function parseArgs(argv) {
  const options = { skill: "unreal" };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--skill") {
      if (!argv[index + 1]) throw new Error("--skill requires a value");
      options.skill = argv[++index];
    } else if (arg === "--skills-dir") {
      if (!argv[index + 1]) throw new Error("--skills-dir requires a value");
      options.skillsDir = expandHome(argv[++index]);
    } else throw new Error(`Unknown option: ${arg}`);
  }
  if (!new Set(["original", "umg", "talent", "unreal", "all"]).has(options.skill)) {
    throw new Error(`Unknown skill selection: ${options.skill}`);
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
    const sourcePath = path.join(source, entry.name);
    const destinationPath = path.join(destination, entry.name);
    if (entry.isDirectory()) copyDirectory(sourcePath, destinationPath);
    else if (entry.isFile()) fs.copyFileSync(sourcePath, destinationPath);
  }
}

function replaceDirectory(source, skillsDir, name) {
  const destination = path.join(skillsDir, name);
  const relative = path.relative(skillsDir, destination);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Unsafe installer destination");
  if (!fs.existsSync(source)) throw new Error(`Cannot find bundled source at ${source}`);
  fs.rmSync(destination, { recursive: true, force: true });
  copyDirectory(source, destination);
  console.log(`Installed ${name}: ${destination}`);
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) return usage();
  const root = path.resolve(__dirname, "..");
  const skillsDir = path.resolve(options.skillsDir || defaultSkillsDir());
  if (skillsDir === path.parse(skillsDir).root) throw new Error("Refusing to install into the filesystem root");
  fs.mkdirSync(skillsDir, { recursive: true });

  const selected = options.skill === "all"
    ? ["original", "umg", "talent"]
    : options.skill === "unreal" ? ["umg", "talent"] : [options.skill];

  if (selected.includes("original")) replaceDirectory(path.join(root, SKILLS.original), skillsDir, SKILLS.original);
  for (const key of ["umg", "talent"]) {
    if (selected.includes(key)) replaceDirectory(path.join(root, ".agents", "skills", SKILLS[key]), skillsDir, SKILLS[key]);
  }
  if (selected.some((key) => key === "umg" || key === "talent")) {
    replaceDirectory(path.join(root, "shared", "prospecting-core"), skillsDir, "unreal-prospecting-core");
    copyDirectory(path.join(root, "fixtures", "prospecting"), path.join(skillsDir, "unreal-prospecting-core", "examples"));
  }
  console.log("Restart Codex before invoking installed skills.");
}

try {
  main();
} catch (error) {
  console.error(`Error: ${error.message}`);
  process.exit(1);
}
