import limits from "./catalogDecimalLimits.json";

export function checkedCatalogDecimal(value, label = "catalog decimal") {
  if (value == null || value === "") return null;
  const message = `Enter a non-negative finite ${label} with at most ${limits.integerDigits} integer digits, ${limits.decimalPlaces} decimal places and ${limits.coefficientDigits} coefficient digits (${limits.inputCharacters} input characters), or leave it unknown.`;
  if (!["string", "number"].includes(typeof value)) throw new Error(message);
  const text = String(value).trim();
  if (text.length > limits.inputCharacters) throw new Error(message);
  const match = text.match(/^\+?(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
  if (!match) throw new Error(message);
  const [whole, fraction = ""] = match[1].split(".");
  const coefficient = (whole + fraction).replace(/^0+/, "") || "0";
  // A bounded exponent is safe to inspect as an integer. The value itself is
  // never passed through Number, expanded, rounded or rewritten.
  const exponentText = (match[2] || "0").replace(/^[+-]?0*/, "");
  if (exponentText.length > 4) throw new Error(message);
  const exponent = Number(match[2] || 0);
  const power = exponent - fraction.length;
  const integerDigits = coefficient === "0" ? 0 : Math.max(coefficient.length + power, 0);
  if (coefficient.length > limits.coefficientDigits || power > limits.integerDigits
      || Math.max(-power, 0) > limits.decimalPlaces || integerDigits > limits.integerDigits) throw new Error(message);
  return text;
}
