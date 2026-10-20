// 探测脚本 v2 —— 写 API（CARDINAL_JS_MODE=write 时由 /osc-js-run 2 执行）
// 契约：脚本被包成 globalThis.result = (function(){ <这里> })(); 用 return 交结果。
const m = cardinal.modules();
const first = parseInt(m.split(",")[0].split(":")[0]);
// 读回改前的显示值——各 quantity 的显示值域不同（VCO param2 是 Hz、
// ADSR 是 ms），所以断言只能「回读值 == 传入的显示值」，不能写死数字。
const before = cardinal.getParam(first, 2);
const r1 = cardinal.setDisplayValue(first, 2, 0.8);
const after = cardinal.getParam(first, 2);
const r2 = cardinal.addModule("Fundamental|VCA-1", 0, 0);
return "setDisplay=[" + r1 + "] addModule=[" + r2 + "]"
  + " before=" + before + " after=" + after;
