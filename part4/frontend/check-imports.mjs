// Finds the two things that build fine on Windows but fail on Vercel (Linux):
//  1) an import whose file name has different upper/lower case than the real file
//  2) an import of a package that is not listed in package.json
// Run from the frontend folder:   node check-imports.mjs
import fs from "fs";
import path from "path";

const root = process.cwd();
const pkg = JSON.parse(
  fs.readFileSync(path.join(root, "package.json"), "utf8"),
);
const known = new Set([
  ...Object.keys(pkg.dependencies || {}),
  ...Object.keys(pkg.devDependencies || {}),
]);
const exts = ["", ".js", ".jsx", ".ts", ".tsx", ".json", ".css"];
const problems = [];

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    const p = path.join(dir, d.name);
    return d.isDirectory() ? walk(p) : /\.(jsx?|tsx?)$/.test(d.name) ? [p] : [];
  });
}

// resolve with exact case; returns {ok, actual}
function exact(p) {
  const parts = path.relative(root, p).split(path.sep);
  let cur = root;
  for (const part of parts) {
    const names = fs.existsSync(cur) ? fs.readdirSync(cur) : [];
    const hit = names.find((n) => n === part);
    if (hit) {
      cur = path.join(cur, hit);
      continue;
    }
    const loose = names.find((n) => n.toLowerCase() === part.toLowerCase());
    return loose
      ? { ok: false, actual: path.join(cur, loose) }
      : { ok: false, actual: null };
  }
  return { ok: true };
}

for (const file of walk(path.join(root, "src"))) {
  const src = fs.readFileSync(file, "utf8");
  const specs = [
    ...src.matchAll(/(?:from\s+|import\s*\(\s*|import\s+)["']([^"']+)["']/g),
  ].map((m) => m[1]);
  for (const s of specs) {
    const rel = path.relative(root, file);
    if (s.startsWith(".")) {
      const base = path.resolve(path.dirname(file), s);
      let best = null,
        found = false;
      for (const e of exts) {
        const r = exact(base + e);
        if (r.ok && fs.statSync(base + e).isFile()) {
          found = true;
          break;
        }
        if (r.actual && !best) best = r.actual;
      }
      if (!found) {
        problems.push(
          best
            ? `CASE MISMATCH in ${rel}: imports "${s}" but the file is "${path.relative(root, best)}"`
            : `MISSING FILE in ${rel}: imports "${s}" but nothing is there`,
        );
      }
    } else if (!s.startsWith("node:") && !s.startsWith("virtual:")) {
      const name = s.startsWith("@")
        ? s.split("/").slice(0, 2).join("/")
        : s.split("/")[0];
      if (!known.has(name))
        problems.push(
          `PACKAGE NOT IN package.json: ${rel} imports "${s}" (run: npm install ${name})`,
        );
    }
  }
}

if (problems.length) {
  console.log("\nProblems found:\n");
  [...new Set(problems)].forEach((p) => console.log(" - " + p));
  console.log(
    "\nFix these, then run `npm run build` and `vercel --prod` again.\n",
  );
  process.exit(1);
}
console.log(
  "\nOK: every import resolves with the right case and every package is in package.json.\n",
);
