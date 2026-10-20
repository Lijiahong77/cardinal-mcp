// 探测脚本 v1 —— 读 API 全跑一遍（/osc-js-run 1 执行）
// 契约：脚本被包成 globalThis.result = (function(){ <这里> })();
// 所以用 return 交结果，不要自己赋 globalThis.result（会被 undefined 覆盖）。
const m = cardinal.modules();
const t = cardinal.transport();
const first = parseInt(m.split(",")[0].split(":")[0]);
const p = cardinal.getParam(first, 2);
const ports = cardinal.ports(first);
const cables = cardinal.cables();
return "modules_len=" + m.length
  + " transport_playing=" + t.includes("playing")
  + " param2=" + p
  + " ports_len=" + ports.length
  + " cables_len=" + cables.length;
