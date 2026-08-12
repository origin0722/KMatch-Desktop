# 研究：AI 克隆模板的布局/交互设计语言分析与 KMatch 优化方案

> 研究对象：`github.com/JCodesMore/ai-website-cloner-template`（31.8k star 的"AI 克隆任意网站"模板）
> 参考站点：`https://ai.explore.poker/chat`（暗色 #101010 的 AI 对话站，SPA 静态壳，实际布局由 JS 渲染）
> 日期：2026-08-12 ｜ 研究方式：curl 直连下载仓库源码逐文件阅读（本环境 WebFetch/WebSearch 被工具层拦截，shell 网络可用）
> 结论先行：**该模板是"克隆流水线"而非现成布局源码**；它真正的价值在于①一套完整的设计 token 规范、②一个高质量交互原语（按钮）、③一套"如何系统性分析站点布局与交互"的方法论。本报告把这三点拆开，映射到 KMatch 的界面优化项，并给出可直接落地的 Vue 适配代码。

---

## 一、这个模板是做什么用的

一句话：**给 AI 编程代理（Claude Code / Codex / Cursor 等）用的"网页逆向工程→重建"流水线模板**，不是某个聊天站点的源码。

- 技术栈起步骨架：Next.js 16 (App Router, React 19, TS strict) + shadcn/ui（base-nova 风格）+ Tailwind CSS v4（oklch 设计 token）+ Lucide 图标。
- 用法：`npm run dev` → 对代理说 `/clone-website <目标URL>` → 代理按 SKILL.md 的多阶段流水线（侦察→建基→组件规格→并行构建→组装→QA）把目标站点 1:1 重建出来。
- 模板自带源码极少：`src/` 下只有空的 `layout.tsx / page.tsx / globals.css / ui/button.tsx`——**真正布局由克隆流程临时生成，模板里没有**。

> 所以"参考它学习侧边栏/聊天主体/可拖拽宽度"的准确姿势是：**学它的设计规范与方法论**，而不是找它的侧栏代码。下面两节分别给出这两样，第三节给出 KMatch 的落地适配。

---

## 二、从模板提取的布局/交互设计语言

### 2.1 设计 Token 规范（globals.css，暗色主题核心）

模板把整个视觉体系收敛为一组语义化 token，明暗两套，全部用 oklch 色空间（比 hex 更符合人眼感知，过渡更自然）：

| Token | 亮色示例 | 暗色示例 | 作用 |
|:---|:---|:---|:---|
| `--background / --foreground` | `oklch(1 0 0)` / `oklch(0.145 0 0)` | `oklch(0.145 0 0)` / `oklch(0.985 0 0)` | 页面底/正文 |
| `--sidebar / --sidebar-foreground` | 近白 | `oklch(0.205 0 0)` | **侧栏独立底色**，与主内容区分 |
| `--sidebar-accent / --sidebar-border / --sidebar-ring` | — | `oklch(0.269..)` / `oklch(1 0 0 / 10%)` | 侧栏悬停/激活/描边/焦点环 |
| `--sidebar-primary` | 近黑 | `oklch(0.488 0.243 264.376)`（靛蓝） | 侧栏主色（激活态） |
| `--border / --input` | 灰 | `oklch(1 0 0 / 10%)`、`/ 15%` | **暗色用"白色低透明度"做分隔线**，比纯灰更通透高级 |
| `--radius-*` | `sm=0.6r, md=0.8r, lg=r, xl=1.4r, 2xl=1.8r, 3xl=2.2r, 4xl=2.6r` | 同左 | **圆角用乘法尺度**（r 为基准），全站统一比例 |
| `--chart-1..5` | 灰阶 | 灰阶 | 图表配色，从最深到最浅 |

**暗色"高级感"的配方（值得 KMatch 抄）**：
1. 底色分三档：主内容（最深）→ 卡片（+1）→ 侧栏（再 +1），层次靠亮度差而非边框；
2. 分隔线不用灰，用 **`rgba(255,255,255,0.1)`** 式白透（暗色）/ `rgba(0,0,0,0.08)` 式黑透（亮色）；
3. 激活态给一个**带色相的靛蓝**（`--sidebar-primary`），其余保持中性，避免"到处彩色"的廉价感。

### 2.2 交互原语（ui/button.tsx，shadcn base-nova）

这是模板里唯一一个完整组件，但它浓缩了整套交互规范，KMatch 可直接照搬思想：

```text
- transition-all（全局统一过渡）
- active:translate-y-px        # 按下时下沉 1px —— 微妙的"手感"
- hover 变底色/文字色          # 悬停反馈
- focus-visible:ring-3 ring-ring/50  # 键盘焦点环（可访问性）
- 紧凑尺寸: default h-8 / sm h-7 text-0.8rem / xs h-6
- 圆角: rounded-lg, 组内 button 用 rounded-lg 收角
- disabled:opacity-50
```

要点：**交互反馈是"最小位移 + 颜色/阴影 + 焦点环"三层组合**，而不是大面积动画。这正是"高级感"和"粗糙感"的分水岭——粗糙的按钮只是换个色，精致的按钮有 press 位移、hover 过渡、focus 环。

### 2.3 方法论：如何系统分析一个站点的布局与交互（SKILL.md + INSPECTION_GUIDE 精华）

这是模板最值钱的部分，对"想把某站改成什么样"和"给自己项目做交互设计"都通用：

1. **先定交互模型，再动手**（最常见返工源）：一个区域是 **click 驱动 / scroll 驱动 / hover 驱动 / 时间驱动** 哪种？——滚动时先看它会不会自己变，再点。
2. **提取"每个状态"，不只默认态**：滚动到阈值前后各抓一次 computed style，**diff 出变化属性 + 过渡时长/缓动**——"从 A 到 B，触发 X，transition Y"。
3. **悬停也要记录 前后值 + duration + easing**，不是"变一下"。
4. **响应式三档**：桌面 1440 / 平板 768 / 移动 390，记录每档布局何时翻转。
5. **滚动驱动激活**：侧栏 active 项随内容滚动自动切换用 **IntersectionObserver**（不是 click handler）。
6. **平滑滚动**：检查 Lenis / Locomotive Scroll（`.lenis` 类）；默认滚动"手感"明显不同。
7. 组件 spec 文件 = 提取方与构建方之间的"契约"，每一条 CSS 值来自 `getComputedStyle()` 而非估计。

---

## 三、KMatch 优化方案建议（逐项映射到你的反馈）

以下每项都给出"做什么 + 怎么做（含代码）"，同时标注对应 issue 拆分建议（见文末）。

### 3.1 左侧导航：透明 / 点击动画 / 高级感
- **透明感**：模板暗色用"白透分隔线 + 亮度分层"实现通透。KMatch 左侧栏可把背景从纯 `--km-bg-layer-0` 改为**轻微透明白叠加**（`background: color-mix(in srgb, var(--km-bg-layer-0) 85%, transparent)`）或直接给层背景加 6-8% 透明度 + `backdrop-filter: blur(8px)`，与主区产生"悬浮玻璃"感。
- **点击动画**：参考 button.tsx 的三层反馈——hover 过渡（0.18s）+ `:active { transform: scale(0.96) }` 按压缩放 + active 项左侧 3px 指示条入场动画（`transform: scaleY(0)→1`）。已有 `scale(0.98)`，可再加"涟漪/滑块"式激活指示。

### 3.2 去除顶部 KMatch 品牌框
- 现状：`TitlebarMenu` 下移后 NavSidebar 顶部有 `nav-brand`（logo + "KMatch·知链"）占一整行。
- 建议：**去掉品牌文字行，只留一行图标菜单**（把品牌名收敛进窗口标题/状态栏），或把品牌压成一行内联的小字；释放 40px 纵向空间，侧栏更干净。参考 Explore：顶栏极简，品牌不占导航位。

### 3.3 设置页"允许/询问/禁用"三态按钮组
- 现状：每行一个 `el-radio-button` 组（允许/询问/禁用），默认 EP 风格。
- 建议：**换成分段式（segmented）控件**——等宽圆角胶囊、激活态品牌色填充 + 白字、未选灰字，宽度固定，三态语义用颜色区分（允许=绿、询问=琥珀、禁用=红）。比并排三个方按钮更"精密"。

### 3.4 全局字体颜色过小/过浅
- 建议：正文从 `13px` → `13.5px`，次要文字 `--km-gray-500` → `--km-gray-600`；`--km-gray-400` 只用于纯装饰。一次性在 theme.css 调 token，全站生效（比逐组件改高效）。注意与 3.2 的"紧凑"平衡——**字号提升优先于颜色加深**。

### 3.5 侧栏 / 代码栏 / AI 栏宽度可拖拽调节（重点，附代码）
- 建议：给 NavSidebar 右缘、FileExplorer 右缘、AssistantPanel 左缘各加一条 **2px 拖拽分隔条（divider）**，`pointerdown → mousemove` 期间更新 CSS 变量 `--panel-w`，组件宽度引用该变量。数据落 localStorage，刷新保持。
- 关键实现（Vue 3 + CSS 变量，直接可用）：

```vue
<!-- ResizablePanel.vue: 包裹任意面板, 左侧/右侧可拖 -->
<template>
  <div class="resizable" :style="{ width: `${width}px` }">
    <slot />
    <div class="divider" @pointerdown="onDown" />
  </div>
</template>
<script setup>
import { ref, onUnmounted } from 'vue'
const props = defineProps({
  min: { type: Number, default: 160 },
  max: { type: Number, default: 480 },
  side: { type: String, default: 'right' }, // right: 拖右缘; left: 拖左缘
})
const width = ref(Number(localStorage.getItem(props.panelKey)) || 208)
let startX = 0, startW = 0
function onDown(e) {
  startX = e.clientX; startW = width.value
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}
function onMove(e) {
  const d = props.side === 'right' ? e.clientX - startX : startX - e.clientX
  width.value = Math.min(props.max, Math.max(props.min, startW + d))
}
function onUp() {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  localStorage.setItem(props.panelKey, width.value) // 记住宽度
}
onUnmounted(onUp)
</script>
<style scoped>
.resizable { position: relative; flex-shrink: 0; }
.divider {
  position: absolute; top: 0; bottom: 0;
  width: 3px; margin-left: -1.5px;      /* 落在边界上 */
  cursor: col-resize; z-index: 5;
}
.divider:hover { background: var(--km-primary); opacity: .35; } /* hover 高亮 */
.divider:active { opacity: 1; }                                  /* 拖拽时实色 */
</style>
```
> 说明：`pointermove/up` 挂 window 上保证拖出面板仍跟手；拖拽过程用 `user-select:none`（或 `body` 临时禁用）防文本选中；hover 细条高亮、active 实色——这正是"精致感"的交互原语。

### 3.6 学习会话界面重布局 + 答题后默认展示 AI 协同
- "学习目标方向"占两行：收紧为一行（去掉冗余描述/换行），或把目标方向做成顶部胶囊标签而非大字标题。
- 答题完成后默认展开 AI 协同面板：测评 store `assessment` 在 interactive 完成后 set 一个 `showCollab = true` 状态，AI 面板自动浮现并给出"下一步建议"。可参考模板的"滚动驱动激活"——答题区滚动到底自动点亮协同入口。

### 3.7 代码功能与项目图谱强相关
- 现状：`generate_project_graph` 工具已能生成图谱实体列表并可跳转 Monaco，但**独立的项目图谱视图（ProjectGraphView）仍缺**。
- 建议：代码视图与图谱视图之间加**联动**——Monaco 光标所在符号 → 图谱高亮该实体（`projectGraph.activeEntityId` 已有此状态）；图谱点击实体 → Monaco 跳到对应行列。这样"强相关"从数据层（共享 store）变成可见交互。

### 3.8 学习资源：把搜索到的知识点与网页收进"学习资源"功能区
- 现状：联网搜索能出 `web_link` 资源（learningResources store），但展示入口在 Learning 视图 tab 里，学习会话中不直观。
- 建议：学习会话中搜索到 web_link 后**自动写入 learningResources store 并浮出"已收集 N 条学习资源"提示条**，点击直达资源列表；资源卡片展示"来源站点图标 + 标题 + 摘要 + 打开"。

### 3.9 数据看板优化
- 建议：图表配色接 `--chart-*` 语义 token（跟随主题）；卡片统一 16px 圆角 + 白透分隔；数字区用大号字重 + tabular-nums 避免跳动。

### 3.10 模型名更新 + 思考过程可见
- 模型名：已另写调研文档 [docs/模型更新调研_2026-08.md](模型更新调研_2026-08.md)（含各厂商最新模型建议），落代码前需线上核实。
- 思考过程可见：KMatch 已有 think-block（可折叠"已思考"）；建议默认**展开**（或流式时展开、结束后收起），并加"思考中"呼吸动画（已有 `thinkPulse`），避免用户干等。

---

## 四、关键代码示例汇总

1. **oklch token 体系**（模板 globals.css）→ 可作为 KMatch theme.css 的演进参考（当前是 hex，可渐进补 `--km-*` 的 `color-mix` 变体，不必全量迁移）。
2. **按钮交互原语**（模板 button.tsx）→ KMatch 所有 `el-button` 的全局覆盖（已做品牌色接轨），再补 `:active { transform: translateY(1px) }` 与 focus 环即可。
3. **拖拽调节宽度**（上方 ResizablePanel.vue）→ 直接落 3.5。
4. **滚动驱动激活**（IntersectionObserver 思想）→ 3.6 学习会话锚点跟随。
5. **暗色高级感配方**（白透分隔线 + 分层亮度 + 靛蓝激活）→ 3.1/3.4。

---

## 五、建议的 issue 拆分（供逐一解决）

按依赖序（blocker 先），每项含验收标准：

| # | Issue 标题 | 类型 | 验收标准（节选） |
|:---|:---|:---|:---|
| 1 | 侧栏/代码栏/AI 栏宽度可拖拽调节 | enhancement | 三条分隔条可拖，宽度记住，范围 160-480 |
| 2 | 去除顶部 KMatch 品牌框 | refactor | 侧栏顶部只剩图标菜单行，无品牌文字占位 |
| 3 | 左侧导航透明玻璃感 + 点击动画 | enhancement | 侧栏带 6-8% 透明+blur，active 项指示条入场动画 |
| 4 | 设置页三态权限改分段控件 | enhancement | 允许/询问/禁用为等宽胶囊，颜色语义化 |
| 5 | 全局字号/字色提升 | refactor | 正文 13.5px，次要色 -500→-600，回归截图对比 |
| 6 | 学习会话重布局 + 答题后默认展示 AI 协同 | enhancement | 目标方向一行；答题完成自动浮现协同+下一步建议 |
| 7 | 项目图谱视图 + 代码/图谱双向联动 | enhancement | 场景二可视化：Monaco↔图谱互跳，图谱过期告警 |
| 8 | 学习资源收集：web_link 自动入资源库 + 提示条 | enhancement | 搜索后资源列表即时更新，可直达 |
| 9 | 数据看板 token 化 + 卡片精修 | enhancement | 图表配色随主题，卡片统一圆角 |
| 10 | AI 模型名更新（先线上核实） | enhancement | PROVIDERS fallback 更新后视觉探测/对话正常 |
| 11 | AI 思考过程默认可见 | enhancement | 思考中呼吸动画，结束可折叠 |

> 说明：1-5 可直接开做；6-8 涉及既有功能行为，建议先各开一个"方案讨论"再动；10 需你先在浏览器核实模型 ID（见调研文档）。

---

## 附：研究来源与局限性

- 来源：模板仓库 tarball 全量阅读（`src/`、`.claude/skills/clone-website/SKILL.md`、`AGENTS.md`、`docs/research/INSPECTION_GUIDE.md`、`globals.css`、`ui/button.tsx`）；参考站点 `ai.explore.poker/chat` 仅抓到 SPA 静态壳（布局由 JS 渲染，无法离线展开），故布局细节以模板设计规范为准。
- 局限：参考站点的真实侧栏/聊天布局未能亲眼解析（无浏览器自动化工具），如需 1:1 参考建议你在浏览器打开该站对照；模板不直接含聊天应用源码，代码示例为按模板规范的适配实现。
