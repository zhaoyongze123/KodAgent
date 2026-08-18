---
name: OA 审批统一工作台
description: 一套服务审批发起、处理与管理配置的统一企业工作台设计系统
colors:
  accent: "#1565c0"
  accent-strong: "#0b57a1"
  accent-soft: "#e7f1fb"
  ink: "#17202d"
  ink-muted: "#4c5b70"
  line: "#d7dee8"
  surface: "#ffffff"
  surface-subtle: "#f3f6fa"
  surface-panel: "#eef2f7"
  dark-accent: "#7cc0ff"
  dark-ink: "#edf3fb"
  dark-ink-muted: "#9eacbf"
  dark-line: "#263243"
  dark-surface: "#101923"
  dark-surface-subtle: "#16212d"
  dark-surface-panel: "#0c141d"
typography:
  body:
    fontFamily: "SF Pro Text, SF Pro Display, PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.6
    letterSpacing: "normal"
  title:
    fontFamily: "SF Pro Text, SF Pro Display, PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.01em"
rounded:
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "24px"
spacing:
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  panel-default:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "20px"
---

# Design System: OA 审批统一工作台

## 1. Overview

**Creative North Star: "安静而高效的审批桌面"**

这套系统不是展示型首页，而是一张持续工作的办公桌面。它需要让用户在统一壳子里完成发起、审批、追踪、通知和流程管理，因此视觉语言要把秩序、状态和操作优先级放在第一位，而不是把每个模块都包装成独立“作品”。

整体气质应偏冷静、专业、精确。界面拒绝蓝紫渐变、玻璃拟态、堆叠卡片和过度圆角，也拒绝把用户端与管理端做成两种人格。它应该更像成熟协作工具的内部工作区，信息密度适中，层级明确，长时间使用不疲劳。

**Key Characteristics:**

- 单一强调色，只用于当前态、主操作和关键状态
- 通过面层、分隔线和留白建立层级，而不是靠大量阴影
- 标题克制，正文稳定，表单与列表优先可读性
- 同一组件语法覆盖壳子、列表、详情、管理页
- 明暗模式使用相同结构，不允许两套割裂的设计逻辑

## 2. Colors

配色采用克制的产品型冷色中性体系，以清晰可读和高频办公耐看为第一目标。

### Primary

- **Process Blue** (`#1565c0`): 主按钮、当前选中、关键统计与可操作状态的唯一强调色。
- **Process Blue Deep** (`#0b57a1`): 主按钮 hover、深色场景中的收束强调。
- **Process Blue Mist** (`#e7f1fb`): 轻提示、选中背景、弱状态容器。

### Neutral

- **Desk Ink** (`#17202d`): 浅色模式主标题和主要信息文本。
- **Desk Ink Muted** (`#4c5b70`): 次级说明、列表辅助信息、标签文案。
- **Shell Line** (`#d7dee8`): 分隔线、输入边框、容器描边。
- **Paper Surface** (`#ffffff`): 主内容面。
- **Mist Surface** (`#f3f6fa`): 工具条、筛选区、空白弱面层。
- **Panel Surface** (`#eef2f7`): 壳子底面、页面背景。

### Dark

- **Night Ink** (`#edf3fb`): 暗色主文本。
- **Night Ink Muted** (`#9eacbf`): 暗色次级文本。
- **Night Surface** (`#101923`): 暗色主面。
- **Night Surface Subtle** (`#16212d`): 暗色次级面层。
- **Night Surface Panel** (`#0c141d`): 暗色页面底面。
- **Night Line** (`#263243`): 暗色分隔与描边。
- **Night Accent** (`#7cc0ff`): 暗色强调色。

### Named Rules

**The One Accent Rule.** 任一页面只允许一个强调色家族。成功、警告、错误只用于语义反馈，不参与装饰。

## 3. Typography

**Display Font:** 无独立展示字体，统一使用系统型无衬线栈  
**Body Font:** SF Pro Text, SF Pro Display, PingFang SC, Microsoft YaHei, ui-sans-serif, system-ui, sans-serif  
**Label/Mono Font:** 继承正文体系，仅在编号和数据处启用 tabular numerals

**Character:** 字体系统应像成熟办公产品，稳定、清晰、无表演感。重点通过字重和间距变化体现，而不是靠夸张字号或装饰性字形。

### Hierarchy

- **Page Title** (600, 24px, 1.3): 用于主区标题和详情标题。
- **Section Title** (600, 18px, 1.35): 用于面板标题、列表栏标题、卡片区标题。
- **Body** (500, 14px, 1.6): 默认正文、筛选项、菜单项、辅助信息。
- **Dense Meta** (500, 12px, 1.5): 标签、时间、流程编号、状态补充信息。
- **Label** (600, 13px, 1.45): 筛选标题、表单字段名、按钮文字。

### Named Rules

**The No Hero Rule.** 这是产品界面，不出现营销式巨型标题，不使用夸张字距和装饰性副标题。

## 4. Elevation

深度以面层和线条为主，阴影只做非常轻的结构分离，不承担“高级感”表达。主内容区、侧栏、工具条之间通过底色变化和 1px 描边区分，避免每个模块都漂浮。

### Shadow Vocabulary

- **Panel Lift** (`0 10px 30px rgba(15, 23, 42, 0.06)`): 仅用于顶层壳子、弹层和少数悬浮区。
- **Hover Lift** (`0 6px 18px rgba(15, 23, 42, 0.08)`): 用于可点击列表行的悬停反馈。

### Named Rules

**The Flat-by-Default Rule.** 静态面板默认平放，只有当前操作对象和顶层浮层才允许轻微抬升。

## 5. Components

### Buttons

- **Shape:** 中等圆角，默认 14px
- **Primary:** 单色填充主按钮，高度 40px，文字始终保持一行
- **Hover / Focus:** 仅允许颜色与边框变化，不使用发光和大面积阴影
- **Secondary / Ghost:** 白底或透明底，依靠描边和文字色区分

### Navigation

- **Top Bar:** 横向产品级导航，不做营销式胶囊秀场
- **Sidebar:** 使用分组和当前态高亮，不包多层卡片
- **Settings Entry:** 系统管理入口收敛到右上角操作组

### Lists

- **Structure:** 优先使用连续列表、分隔线和固定列，而不是重复卡片
- **Selection:** 当前项通过底色、左侧线性强调或描边表达
- **Density:** 支持桌面分屏和全屏办公，不依赖大留白

### Cards / Containers

- **Corner Style:** 页面大容器 24px，普通面板 18px，控件 14px
- **Background:** 纯面色，避免透明玻璃
- **Shadow Strategy:** 只有壳子级和浮层级允许轻阴影
- **Border:** 默认使用细描边建立结构

### Inputs / Fields

- **Style:** 统一浅色底或暗色底输入框，边框清晰
- **Focus:** 1px 边框加轻微外环，不使用霓虹 glow
- **Error / Disabled:** 依靠语义色和文本提示，不只改边框

## 6. Do's and Don'ts

- Do: 用列表和工具条表达审批流，保持信息连续性。
- Do: 让状态、时间、发起人、编号这类元信息稳定对齐。
- Do: 在浅色和暗色模式下维持同样的层级结构与可读性。
- Don't: 在每一层都套圆角卡片和阴影。
- Don't: 默认使用蓝紫渐变、玻璃模糊、营销页式标题。
- Don't: 混用多种图标性格或让不同页面像不同产品。
