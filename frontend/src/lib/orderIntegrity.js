// Compare decimal values without rounding an invoice/order string through Number.
export function sameOrderDecimal(left,right) {
  if (left==null || right==null) return left==null && right==null;
  const normalized=value=>{
    const match=String(value).trim().match(/^([+-]?)(\d+(?:\.\d*)?|\.\d+)(?:e([+-]?\d+))?$/i);
    if(!match)return null;
    const [whole,fraction=""]=match[2].split(".");
    let digits=(whole+fraction).replace(/^0+/,"");
    if(!digits)return "0";
    let power=Number(match[3]||0)-fraction.length;
    if(!Number.isSafeInteger(power))return null;
    const tail=digits.match(/0+$/)?.[0].length||0;
    digits=digits.slice(0,digits.length-tail);power+=tail;
    return `${match[1]==="-" ? "-" : ""}${digits}e${power}`;
  };
  const a=normalized(left);return a!=null && a===normalized(right);
}
