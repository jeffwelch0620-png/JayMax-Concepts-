// Planning units only; native physical profiles keep their independently verified factors.
export const UOM_FAMILY = {
  lb: "weight", oz: "weight", kg: "weight", g: "weight",
  gal: "volume", qt: "volume", pt: "volume", cup: "volume", "fl oz": "volume", l: "volume", ml: "volume",
  each: "count", ct: "count", dozen: "count",
};
export const CONV_TO_BASE = {
  lb: 16, oz: 1, kg: 35.27396195, g: 0.03527396195,
  gal: 128, qt: 32, pt: 16, cup: 8, "fl oz": 1, l: 33.814, ml: 0.033814,
  each: 1, ct: 1, dozen: 12,
};
