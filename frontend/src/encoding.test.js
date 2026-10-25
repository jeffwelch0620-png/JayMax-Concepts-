import fs from "fs";
import path from "path";
import { TextDecoder } from "util";

// Escapes keep the guard's own source clean. Do not ban legitimate accented text.
const broken = /\u00c3\u201a\u00c2\u00b7|\u00c2\u00b7|\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a6|\u00e2\u20ac[\u00a6\u201c\u201d\u2122]/;
function javascriptFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const name = path.join(directory, entry.name);
    return entry.isDirectory() ? javascriptFiles(name) : entry.isFile() && name.endsWith(".js") ? [name] : [];
  });
}
test("all frontend JavaScript is valid UTF-8 without known encoding corruption", () => {
  const files = javascriptFiles(__dirname), decoder = new TextDecoder("utf-8", { fatal: true });
  expect(files.length).toBeGreaterThan(0);
  for (const file of files) {
    const source = decoder.decode(fs.readFileSync(file));
    expect({ file: path.relative(__dirname, file), corrupted: broken.test(source) }).toEqual({ file: path.relative(__dirname, file), corrupted: false });
  }
});
test("the encoding guard detects broken punctuation while accepting valid Unicode", () => {
  expect(broken.test("Retained request \u00c3\u201a\u00c2\u00b7 date")).toBe(true);
  expect(broken.test("Loading\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a6")).toBe(true);
  expect(broken.test("São, Ângela, Ã, café, ·, …, 🍲")).toBe(false);
});
