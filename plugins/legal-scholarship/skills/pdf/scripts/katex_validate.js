// Batch-validate LaTeX strings with the real KaTeX engine.
//
// Usage: node katex_validate.js <path-to-katex-module> <path-to-json-input>
//   input  JSON: an array of LaTeX strings (display-math bodies).
//   output JSON (stdout): an array of booleans — true = renders without a parse
//                         error, false = KaTeX throws.
//
// This is the authoritative oracle behind sanitize_math.py: a block is only
// suppressed when KaTeX cannot render it.
const fs = require("fs");
let katex;
try {
  katex = require(process.argv[2]);
} catch (e) {
  process.stderr.write("KATEX_LOAD_ERROR: " + e.message + "\n");
  process.exit(2);
}
let items;
try {
  items = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
} catch (e) {
  process.stderr.write("INPUT_READ_ERROR: " + e.message + "\n");
  process.exit(3);
}
const ok = items.map((s) => {
  try {
    katex.renderToString(s, { throwOnError: true, displayMode: true, strict: false });
    return true;
  } catch (e) {
    return false;
  }
});
process.stdout.write(JSON.stringify(ok));
