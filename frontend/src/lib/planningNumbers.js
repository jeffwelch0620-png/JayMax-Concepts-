// Finite planning estimates; retained catalog decimals and Track 1 stay exact.
export function planningNumber(value, fallback = null) {
  if (value == null || value === "") return fallback;
  if (typeof value === "boolean" || String(value).trim() === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number) || (number === 0 && /[1-9]/.test(String(value).split(/[eE]/)[0]))) return null;
  return number;
}

export function planningProduct(...values) {
  let result = 1;
  for (const raw of values) {
    const value = planningNumber(raw);
    if (value == null) return null;
    const next = result * value;
    if (!Number.isFinite(next) || (next === 0 && result !== 0 && value !== 0)) return null;
    result = next;
  }
  return result;
}

export function planningQuotient(numerator, denominator) {
  const n = planningNumber(numerator), d = planningNumber(denominator);
  if (n == null || d == null || d === 0) return null;
  const result = n / d;
  return Number.isFinite(result) && !(result === 0 && n !== 0) ? result : null;
}

export function planningSum(values) {
  let result = 0;
  for (const raw of values) {
    const value = planningNumber(raw);
    if (value == null || !Number.isFinite(result + value)) return null;
    result += value;
  }
  return result;
}
