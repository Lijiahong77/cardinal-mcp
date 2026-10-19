# 风格 Schema（STYLE-SCHEMA）— 把「风格怎么搭」变成可流转的 JSON

> 批次 A11（源自 YuE2 借鉴计划①）。配套工具：`tools/style_schema.py`。
> 借鉴 YuE2-Studio 的关键：风格字段要**可编辑、可存 JSON、在工具间流转**，不是写死的散文。

## 一、schema 是什么、给谁用

一份 style JSON = 「这种风格的搭法」的**结构化决策记录**。用途：

1. **李说「做个 XX 风格」** → 先起草一份 style JSON（`draft_from_patch` 或手写）→ 李点头 → 再动手机架。
   （宪法：别替李决定——schema 就是「把候选摆好、数据摊开」的载体。）
2. 下次复刻同风格：直接读上次存的 JSON，**选型和分层不用重新猜**。
3. 消费方：`musiclib.apply_recipe`（参数目标）、未来的生成器。

## 二、七个字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | 非空字符串 | 风格名，人类可读，如 "yorushika-like J-rock ballad" |
| `reference` | 字符串 | 样板 `.vcv` 文件名（**平铺在 patches/ 下，无目录层级**——写成 `yorushika_shura/hana` 是错的，见 TODO E9） |
| `bpm` | `{min, max, actual?}` | min≥40，max≤240 且 ≥min；`actual` 是实测（Clocked param0 = 绝对 BPM，本仓库唯二绝对量纲之一） |
| `layers` | `[{role, job, modules[]}]` | **分层职责——本 schema 的核心**。role 固定词表：`drums/bass/harmony/melody/texture/pad`；job = 这层在织体里干什么（一句话）；modules = 担当该层的模块 model |
| `reverb` | `{model, size, decay}` | 可缺省（干声风格不给）；给了必须含 model |
| `filter` | `{job, openness}` | 滤波开合倾向：job 一句话，openness 0..1 越大越亮 |
| `choices` | `[{module, why}]` | 参考模块选型+理由。缺了只告警不挡门，但下次复刻只能从头猜 |

## 三、API 与流转

```bash
PY="<USERPROFILE>/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe"

# 从已验收机架起草（实测字段自动回填，判断留给人）
python style_schema.py draft quadeca_life1_wdtg.vcv > style_quadeca.json

# 校验（人工补完后）
python style_schema.py validate style_quadeca.json     # 退出码 0 = 通过
```

**分工铁律（机器不替李拍板）**：`draft_from_patch` 只回填**实测值**
（bpm.actual、模块角色清单），`name / bpm 区间 / layers[].job / reverb 数值 /
choices 理由`一律留人。草案里 `_draft_note` 会写明这一点。

## 四、样板回填 ①：quadeca_life1_wdtg（已验收）

```json
{
  "name": "quadeca-like haunt folk（鬼魂民谣）",
  "reference": "quadeca_life1_wdtg.vcv",
  "bpm": {"min": 70, "max": 90, "actual": 96.0},
  "layers": [
    {"role": "harmony", "job": "中音和声垫，铺在旋律下面",
     "modules": ["Plaits"]},
    {"role": "melody", "job": "听感主线，高音区",
     "modules": ["Bogaudio-VCO"]},
    {"role": "texture", "job": "颗粒/拖尾氛围层",
     "modules": ["Elements"]}
  ],
  "reverb": {"model": "Plateau", "size": 0.8, "decay": 0.7},
  "filter": {"job": "整体偏暗，切掉刺耳高频", "openness": 0.4},
  "choices": [
    {"module": "AudibleInstruments|Plaits", "why": "宏振荡器内含几十种乐器模型，一个模块试出方向"},
    {"module": "AudibleInstruments|Elements", "why": "模态合成做'什么材质在响'"}
  ]
}
```

## 五、样板回填 ②：yorushika_hana

```json
{
  "name": "yorushika-like J-rock ballad",
  "reference": "yorushika_hana.vcv",
  "bpm": {"min": 70, "max": 85, "actual": 78.0},
  "layers": [
    {"role": "melody", "job": "主旋律线，MiniArranger 单轨",
     "modules": ["Starsea-MiniArranger"]},
    {"role": "harmony", "job": "弦乐铺底跟和弦走",
     "modules": ["Starsea-MiniArrangerExpander"]}
  ],
  "reverb": {"model": "Plateau", "size": 0.7, "decay": 0.8},
  "filter": {"job": "副歌开大主歌收小，情绪随段落", "openness": 0.55},
  "choices": [
    {"module": "Starsea|Starsea-MiniArranger",
     "why": "8 轨分轨录和弦，每轨独立音色链——本仓编排主线"}
  ]
}
```

> ⚠️ 上面两份的 `bpm.actual` 与 `module_roles` 是从已验收机架**实测回填**的；
> 层职责的 job 文字与 reverb 数值是示例写法，正式收录前须李听过点头。

## 六、为什么长这样（抄 YuE2 抄什么）

- **可编辑可流转**：style = 纯 JSON，`dump_style()` 存盘后在 draft → validate →
  recipe 之间传，不锁在任何工具里。
- **字段是决策不是散文**：分层职责（job）与选型理由（choices.why）强制成文——
  复刻风格时最贵的不是参数，是「当时为什么选它」。
- **实测与判断分离**：`draft_from_patch` 只回填机器能实测的（BPM、模块清单），
  判断字段（职责/区间/数值）留空等人拍板——同宪法「别替李做决定」。
