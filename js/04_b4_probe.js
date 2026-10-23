// B4 验收探针 —— 进程内直读 MiniArranger 的 arranger.tracks[].measures
// 契约：脚本被包成 IIFE，用 return 交结果。
// 背景：OSC set param 13 = 8 后，display_value 读回 8.0，但 save_live（走 autosave
// 文件）读到 measures 仍是 [4,4,4,4]。此探针绕开 autosave，直读引擎内 JSON。
const MA_ID = 7100000000000003;
const j = cardinal.moduleJson(MA_ID);
if (!j || j.length < 10) return "moduleJson EMPTY/FAIL len=" + (j ? j.length : -1);
let o;
try { o = JSON.parse(j); } catch (e) { return "JSON parse fail: " + e; }
const d = o.data || {};
const arr = d.arranger || {};
const tr = arr.tracks || [];
const ms = [];
for (let i = 0; i < tr.length; ++i) ms.push(tr[i].measures);
// param 13（B4 新旋钮）的存储值
const ps = o.params || [];
const p13 = ps.length > 13 ? ps[13] : null;
return "editTrack=" + arr.editTrack
  + " measures=[" + ms.join(",") + "]"
  + " param13=" + (p13 === null ? "MISSING(numParams=" + ps.length + ")" : p13)
  + " params_len=" + ps.length;
