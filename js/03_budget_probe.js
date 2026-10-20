// 探测脚本 v3 —— 指令预算中断（CARDINAL_JS_MODE=read 时 /osc-js-run 3 执行）
// 契约：脚本被包成 globalThis.result = (function(){ <这里> })(); 用 return 交结果。
// 这个死循环若不被打断，会把 OSC handler 所在的 UI 线程永久卡死——
// 预算机制（oscJsInterrupt）必须在运行级真验，不能只看代码。
let n = 0;
while (true) {
  n = n + 1;
}
return "NOT REACHED n=" + n;