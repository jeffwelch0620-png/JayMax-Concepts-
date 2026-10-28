// Read projection only: bounded decimal text, no binary quantity arithmetic.
// Wider native derived quantities are held rather than rounded.
export function overviewDecimal(value) {
  if (typeof value !== "string" || value.length > 42 || !/^\d{1,28}(?:\.\d{1,12})?$/.test(value)) {
    throw new Error("Quantity precision or value is not supported.");
  }
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole + fraction.padEnd(12, "0"));
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
