// Read projection only: bounded decimal text, no binary quantity arithmetic.
// Wider native derived quantities are held rather than rounded.
// Accepts plain decimals and the exponent form Python's str(Decimal) emits for native
// quantities (e.g. "0E-12", "1E-12", "1.5E+3"), converted exactly before the bounds apply.
const SCALE = 12, LIMIT = 10n ** 40n; // at most 28 integer and 12 fractional digits
export function overviewDecimal(value) {
  const match = typeof value === "string" && value.length <= 60 && /^(\d+)(?:\.(\d+))?(?:E([+-]?\d{1,3}))?$/.exec(value);
  if (!match) throw new Error("Quantity precision or value is not supported.");
  const [, whole, fraction = "", exponent = "0"] = match;
  const shift = Number(exponent) - fraction.length + SCALE;
  let scaled = BigInt(whole + fraction);
  if (shift >= 0) scaled *= 10n ** BigInt(shift);
  else {
    const divisor = 10n ** BigInt(-shift);
    if (scaled % divisor !== 0n) throw new Error("Quantity precision or value is not supported.");
    scaled /= divisor;
  }
  if (scaled >= LIMIT) throw new Error("Quantity precision or value is not supported.");
  return scaled;
}
export function decimalText(value) {
  const digits = value.toString().padStart(13, "0");
  const whole = digits.slice(0, -12), fraction = digits.slice(-12).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}
export function overviewDifference(planned, reviewed) {
  const difference = overviewDecimal(planned) - overviewDecimal(reviewed), zero = BigInt(0);
  return { remaining: decimalText(difference > zero ? difference : zero),
    excess: decimalText(difference < zero ? -difference : zero) };
}
