# 项目语义图谱设计：Agent 驱动的多语言框架理解

> 状态：已获产品方向确认，等待设计文档复核后再拆实施计划  
> 日期：2026-09-02  
> 关联：[画像协同历史与体验升级总方案](../../项目规划/2026-09-02_画像协同历史与体验升级总方案.md)

## 1. 问题与目标

KMatch 当前的项目图谱是 **Python 代码结构图谱**：前端读取 `.py` 文件，后端用 Python AST 和 Jedi 提取符号、调用和关系。它不能理解 Java、TypeScript、Rust、C 等项目的结构，也不能可靠地回答“这个项目采用了什么框架、请求如何进入业务层、配置与数据模型如何连接”。

本设计将项目图谱升级为 **项目语义图谱（Project Semantic Graph）**：Agent 读取项目目录、构建文件、依赖、配置、源码和测试，以可追溯证据为前提，构建可解释的架构与框架关系图。

### 1.1 产品目标

- 用户打开一个项目后，能看到它的语言、构建工具、主要框架和检测置信度；
- 用户能从运行入口或 API 路由，追踪到 Controller/Handler、业务服务、数据访问、实体/数据表、配置与测试；
- 图谱能按“架构”“框架流程”“代码细节”“配置与依赖”“质量证据”切换；
- 每个框架角色和关系均能回跳真实文件、行号、manifest/config 或测试结果；
- 对不认识的语言或框架，系统仍提供可靠的结构图谱，并明确说明能力边界；
- Agent 过程透明地展示扫描、识别、提取、审核和降级，但不展示隐藏思维链或原始私密提示词；
- 第一阶段完整支持 Spring Boot，第二阶段支持 TypeScript + NestJS，现有 Python 项目图谱迁移到统一适配器框架。

### 1.2 非目标

- 不承诺一次支持所有语言、所有框架或运行时动态行为；
- 不把 LLM 推断伪装成静态事实；
- 不直接执行未知项目代码；
- 不自动修改用户源码；
- 不在第一阶段实现 JavaScript、Rust、C 的完整框架语义；
- 不用“全量上传项目”换取理解效果，必须有范围、忽略规则和文件上限。

## 2. 术语与边界

| 术语 | 精确定义 |
|---|---|
| 项目侦察 | 读取目录、文件类型、构建文件、依赖、配置、测试与入口的只读阶段。 |
| 结构图谱 | 基于解析器得到的文件、模块、符号、导入、调用、继承/实现、构建依赖关系。 |
| 框架图谱 | 在结构图谱之上，经过框架适配器与证据审核确认的框架角色和调用/数据流。 |
| 项目语义图谱 | 结构图谱、框架图谱、配置/依赖和质量证据的统一产物。 |
| 语言适配器 | 负责某语言的文件选择、语法/语义解析、符号和基础关系抽取。 |
| 框架适配器 | 负责某框架的特征识别、角色映射、框架关系提取和置信度规则。 |
| 证据 | 支撑一个节点或边的文件路径、行号、文本片段 hash、配置项、依赖项或测试结果。 |
| 已验证关系 | 有确定性解析或框架规则证据的关系。 |
| 推断关系 | LLM 或启发式提出但证据不足以确认的关系；默认不进入正式框架路径。 |

产品对外表述：**KMatch 是多领域个性化学习引擎；项目语义图谱按已支持的语言与框架提供分级理解。** 不把“可读取文件”称作“完整支持框架”。

## 3. 方案选择

### A. 文件依赖图扩展

读取更多后缀，显示 import/include 和文件依赖。

- 优点：实现最快，语言覆盖多；
- 缺点：无法展示框架分层、依赖注入、路由或数据模型；不能满足“理解项目框架”的目标；
- 结论：仅作为所有语言的结构图谱底座，不作为最终方案。

### B. 纯 LLM 项目总结

让 Agent 阅读文件后直接生成“框架解释”和图谱。

- 优点：短期看上去覆盖广；
- 缺点：易产生幻觉、关系无法证实、成本和上下文不可控；
- 结论：不用作图谱真相源。LLM 只可在候选框架识别、解释摘要和低置信度建议中使用。

### C. 混合式项目语义图谱（采用）

以确定性项目侦察、语言解析和框架规则为事实底座；Agent 负责编排、补全解释、证据审核和可视化叙述。

- 优点：既能解释框架，又能追溯和测试；新语言/框架可以通过 Adapter 增量接入；
- 代价：需要先建设统一数据模型与适配器边界；
- 结论：采用。

## 4. 目标架构

```text
项目根目录（只读、已过滤）
  │
  ├─ 项目侦察 Agent
  │    ├─ ProjectScan：文件清单、语言、构建/配置/测试清单
  │    └─ FrameworkCandidate：候选框架 + manifest/config 证据
  │
  ├─ LanguageAdapter（Python / Java / TypeScript / …）
  │    └─ StructuralGraph：文件、模块、符号、调用、导入、实现
  │
  ├─ FrameworkAdapter（Spring Boot / NestJS / …）
  │    └─ SemanticOverlay：框架角色、路由、DI、ORM、配置关系
  │
  ├─ 框架理解 Agent
  │    └─ 生成受证据约束的架构摘要、术语解释与学习建议
  │
  ├─ 证据审核 Agent
  │    └─ 校验每条关系的证据、置信度、冲突与降级原因
  │
  └─ ProjectSemanticGraph
       ├─ 架构视图
       ├─ 框架流程视图
       ├─ 代码细节视图
       ├─ 配置/依赖视图
       └─ 风险、测试、Agent 证据视图
```

### 4.1 Agent 职责

| Agent/组件 | 输入 | 输出 | 不负责 |
|---|---|---|---|
| 项目侦察 Agent | 文件树、manifest、配置文件 | `ProjectScan`、语言/框架候选 | 解释业务正确性 |
| 语言适配器 | 允许的源码文件 | 符号、结构关系、解析诊断 | 推断框架角色 |
| 框架适配器 | 结构图、manifest、配置 | 框架角色、语义关系、规则证据 | 编造未命中的框架关系 |
| 框架理解 Agent | 已验证图谱与证据摘要 | 面向用户的架构解释、学习入口 | 覆盖或修改图谱事实 |
| 证据审核 Agent | 所有候选节点/边与证据 | 状态、置信度、冲突、降级报告 | 暴露模型私有思维链 |
| 项目质量流水线 | 已选择的文件/模块与图谱 | 审查、测试、修复建议产物 | 无确认地写回源码 |

### 4.2 证据不变量

正式显示的框架节点或边必须至少满足一项：

1. 语言解析器给出确定性 AST/符号关系；
2. manifest、依赖锁、构建文件或配置文件命中已登记框架特征；
3. 框架适配器规则命中源码注解、基类、接口、装饰器、宏或约定目录；
4. 测试、构建输出或运行配置提供补充证据。

每条关系保存 `evidence_refs`、`confidence`、`source_kind` 和 `verification_status`。没有足够证据的候选只进入“待确认推断”抽屉，不能成为默认调用链的一部分。

## 5. 统一数据模型

```json
{
  "project_id": "workspace:demo-shop",
  "snapshot_id": "psg_20260902_001",
  "scan": {
    "languages": [{"id": "java", "files": 48, "confidence": 1.0}],
    "build_tools": [{"id": "maven", "file": "pom.xml"}],
    "framework_candidates": [{
      "id": "spring-boot",
      "confidence": 0.98,
      "evidence_refs": ["pom.xml#spring-boot-starter-web", "UserController.java:12"]
    }]
  },
  "nodes": [{
    "id": "java:UserController",
    "kind": "class",
    "framework_role": "controller",
    "label": "UserController",
    "file": "src/main/java/.../UserController.java",
    "range": {"start_line": 12, "end_line": 44},
    "confidence": 1.0,
    "evidence_refs": ["UserController.java:12:@RestController"]
  }],
  "edges": [{
    "id": "edge:route:create-user",
    "kind": "ROUTES_TO",
    "from": "route:POST:/api/users",
    "to": "java:UserController#create",
    "verification_status": "verified",
    "confidence": 1.0,
    "evidence_refs": ["UserController.java:23:@PostMapping"]
  }],
  "diagnostics": [],
  "capabilities": {
    "structural_graph": "supported",
    "framework_graph": "supported",
    "quality_pipeline": "available"
  }
}
```

节点类别统一包括：`project`、`module`、`file`、`package`、`class`、`interface`、`function`、`route`、`controller`、`service`、`repository`、`entity`、`dto`、`config`、`dependency`、`database_table`、`test`、`task`、`driver`。

边类别统一包括：`CONTAINS`、`IMPORTS`、`CALLS`、`IMPLEMENTS`、`EXTENDS`、`INJECTS`、`ROUTES_TO`、`DELEGATES_TO`、`PERSISTS_WITH`、`MAPS_TO`、`CONFIGURES`、`DEPENDS_ON`、`TESTS`、`EXPOSES_API`、`FFI_CALLS`。

## 6. 第一阶段：Spring Boot 框架图谱

### 6.1 识别范围

- Maven/Gradle：`pom.xml`、`build.gradle`、`settings.gradle`；
- 配置：`application.yml`、`application.properties`、profiles；
- Web：`@SpringBootApplication`、`@RestController`、`@Controller`、`@RequestMapping`、`@GetMapping`、`@PostMapping` 等；
- 分层：`@Service`、`@Repository`、构造器注入、`@Autowired`；
- 数据：`@Entity`、`@Table`、`@Id`、JPA Repository、常用 relation 注解；
- 传输：DTO、Mapper、常见请求/响应类型；
- 质量：JUnit/Mockito 测试文件、构建/测试任务的可执行性诊断。

### 6.2 主要视图

1. **架构视图**：按 Web、Application、Domain、Infrastructure、Configuration、Test 分区；
2. **请求流程视图**：选择 API route 后展示 Route → Controller → Service → Repository → Entity/Table；
3. **数据流视图**：选择 Entity 后展示关联、Repository、DTO/Mapper；
4. **配置依赖视图**：Spring profile、数据源、Maven/Gradle 依赖与运行入口；
5. **质量证据视图**：风险、测试、覆盖率、Agent 审查结论和源码证据。

### 6.3 已知限制

- 反射、动态代理、复杂 SpEL 和运行时自动装配不能保证完整还原；
- 通过约定而非注解实现的自定义分层应标为启发式，不能显示为已验证；
- 多模块 Maven/Gradle 项目第一版只支持有限深度和显式模块依赖；
- 数据库表映射以 JPA 注解和配置为准，不连接真实生产数据库；
- 第三方 SDK 内部实现不展开，只展示依赖边界。

## 7. 后续语言与框架路线

| 阶段 | 语言/框架 | 最低交付 | 框架语义交付 |
|---|---|---|---|
| 0 | Python（已有） | 迁移至统一 `LanguageAdapter` 结果 | 现有调用/实体关系，保留 pytest 质量链 |
| 1 | Java + Spring Boot | Java 包、类、接口、调用、Maven/Gradle | 路由、分层、DI、JPA、配置、JUnit |
| 2 | TypeScript + NestJS | TS 模块、类、import、调用、package.json | Module、Controller、Service、Decorator、DTO、ORM、测试 |
| 3 | JavaScript + Express | Node 模块、require/import、路由、package.json | Route、Middleware、Controller/Service 的规则化识别，降低动态关系置信度 |
| 4 | Rust + Axum/Actix | crate、module、struct、trait、function、Cargo | Router/Handler、State、异步任务、Diesel/SQLx 的已支持特征 |
| 5 | C/CMake 与嵌入式 profile | 源/头文件、include、函数调用、CMake target | 先选择 FreeRTOS 或 Zephyr 之一，识别 task/queue/interrupt/driver/config |

Rust 和 C 不是“不能支持”，但必须在框架 profile 明确后承诺语义图谱。未命中 profile 时提供结构图谱、构建依赖和架构解释，不声称已理解全部框架行为。

## 8. 项目侦察与适配器接口

### 8.1 ProjectScanner

输入项目根目录和用户选择范围，输出忽略后的文件清单、语言统计、manifest/config/test 候选和入口候选。

约束：

- 默认忽略依赖、构建产物、二进制、大文件、密钥和用户配置；
- 首次扫描只读取元数据和允许的文本文件；
- 展示“将读取的文件数、语言、大小、忽略规则”；
- 允许用户将范围缩小为模块或变更文件；
- 不执行构建命令、脚本、安装命令或项目源码。

### 8.2 LanguageAdapter

```text
supports(scan) -> Capability
extract_structure(files, options) -> StructuralGraph
locate_symbol(query) -> SourceLocation[]
diagnostics() -> ParseDiagnostic[]
```

Parser 可采用 Tree-sitter 作为多语言语法底座；Java、Rust、C/C++ 等需要按需接入语言服务器或编译数据库来提高跨文件语义精度。Tree-sitter 只能提供语法结构，不应单独承担类型解析和完整调用解析。

### 8.3 FrameworkAdapter

```text
detect(scan, structural_graph) -> FrameworkMatch[]
enrich(match, structural_graph, configs) -> SemanticOverlay
explainable_rules() -> FrameworkRule[]
```

每个 `FrameworkRule` 需声明：命中特征、产出角色/关系、最低证据数、默认置信度、限制说明和测试 fixture。

## 9. Agent 协同与透明性

一次项目图谱运行使用阶段实例，而不是模糊的 Agent 名称：

```text
scan-project -> detect-framework -> extract-structure -> enrich-framework
-> verify-evidence -> render-graph -> optional-quality-pipeline
```

每个阶段产生结构化事件：`run_id`、`stage_id`、输入摘要、文件计数、候选框架、证据数、输出计数、耗时、状态、降级原因。前端可展示：

- 项目侦察到什么；
- 为什么认定为某框架；
- 哪些关系是已验证、哪些是推断；
- 哪些文件没有被读取或不能解析；
- 质量检查是否运行、运行在哪个范围；
- 如何从节点回到源码和配置。

不显示隐藏思维链。Agent 给出的文字解释必须从 `ProjectSemanticGraph` 和 `evidence_refs` 生成，不能引入未验证事实。

## 10. 降级与错误处理

| 情况 | 行为 | 用户可见说明 |
|---|---|---|
| 未识别语言 | 文件清单与项目侦察报告 | “当前语言无解析器，未生成代码结构图谱” |
| 语言可解析、框架未识别 | 生成结构图谱 | “已展示代码结构，尚无对应框架适配器” |
| 框架候选证据不足 | 展示候选与证据，不启用框架流程 | “框架识别置信度不足，未将关系作为事实展示” |
| 部分文件语法失败 | 保留成功结果和诊断 | “N 个文件无法解析，未参与图谱” |
| 项目过大 | 预览、筛选与增量分析 | “已按范围/忽略规则分析，未读取全部文件” |
| 测试工具不可用 | 保存静态图谱、跳过动态质量结果 | “未运行测试：缺少 Maven/Gradle/npm/Cargo 或沙箱能力” |

## 11. UI 与交互

### 11.1 打开项目后的流程

1. 读取项目清单，显示语言、框架候选、文件范围与隐私提示；
2. 用户确认分析范围；
3. 运行阶段时间线实时显示；
4. 图谱先呈现结构层，再叠加已验证的框架层；
5. 用户可切换架构、流程、代码、配置、质量五个视图；
6. 选择节点后可看到角色、描述、证据、置信度、关联关系、源码跳转和“问 AI”；
7. 运行结果保存为可回看的 `project_semantic_graph` artifact。

### 11.2 视觉规则

- 框架角色使用规范图标和分区，不用 Emoji 作为状态语义；
- 已验证关系为实线，推断关系为虚线且默认隐藏；
- 节点名称旁不堆技术细节，详情抽屉显示注解、配置和引用；
- 框架未识别时不展示空白画布，显示结构图谱和能力边界；
- 大项目按子图、层级聚合和按需展开，避免初始渲染所有符号。

## 12. 测试与验收

### 12.1 单元和契约测试

- `ProjectScanner` 忽略规则、文件上限、manifest/config 发现；
- 每个 `LanguageAdapter` 的符号、导入、调用、解析失败 fixture；
- Spring Boot 规则：Controller、Route、Service、Repository、Entity、JPA relation、config、Maven/Gradle；
- 每个正式框架节点/边都有至少一个 `evidence_ref`；
- 无证据候选不能进入已验证调用链；
- 旧 Python 项目图谱输出经适配后保持关键节点/边等价；
- 运行事件按 `stage_id` 记录并可回放。

### 12.2 集成测试

- 小型 Spring Boot 单模块项目：完整 Route → Controller → Service → Repository → Entity；
- 多模块 Maven 或 Gradle 项目：模块依赖和限定范围；
- 有语法错误的 Java 文件：部分成功、诊断清晰；
- 无 Spring 框架的纯 Java/Cargo/CMake 项目：只提供结构图谱；
- 混合语言项目：各语言结构图可并存，跨服务 REST/配置关系带证据；
- 无网络、无模型或无沙箱：静态图谱仍可生成，降级明确。

### 12.3 人工验收

- 用户在 30 秒内能回答“项目采用什么框架、证据是什么”；
- 用户在 3 次点击内能从 API route 找到数据库实体或无法确认的边界；
- 用户能区分“验证关系”和“推断关系”；
- 用户能跳回任意核心节点的源文件和行号；
- 图谱不因未知框架而假装完整；
- 评委可从 Agent 阶段和证据证明项目理解过程可追溯。

## 13. 交付顺序与风险控制

### Phase A：打地基

- 修复当前 Python pipeline 未定义 store 的缺陷；
- 将 Python 图谱输出封装为 `StructuralGraph`；
- 增加 ProjectScanner、统一证据模型、阶段事件和 artifact 存储；
- 保持现有 Python 解析/测试稳定，不删除现有功能。

### Phase B：Spring Boot 完整纵切

- Java 结构解析；
- Maven/Gradle、配置与框架检测；
- Spring Boot 语义覆盖；
- 五个图谱视图和源码跳转；
- 静态质量证据与可选 Maven/Gradle 测试预检。

### Phase C：TypeScript + NestJS

- 复用 ProjectScanner、图谱模型、事件、UI 和证据机制；
- 新增 TS 结构解析和 NestJS 适配器；
- 再决定 Express 是否按规则化 profile 加入。

### Phase D：Rust/C profile

- 先提供结构图谱；
- 选择一个明确的 Rust Web profile（Axum 或 Actix）和一个 C profile（FreeRTOS 或 Zephyr）；
- 只有在固定 fixture、规则和测试完成后升级为框架图谱。

### 13.1 主要风险

| 风险 | 控制 |
|---|---|
| LLM 将框架猜测当事实 | 结构解析和框架规则为真相源；无证据关系不能进入主图 |
| 多语言一次铺开失控 | 单框架纵切；每阶段只增加一个语言/框架 profile |
| 大项目读取过慢或泄露文件 | 范围预览、忽略规则、大小限制、增量解析和本地落盘 |
| Java/Rust/C 语义解析复杂 | 先保证结构图，再按框架规则加 overlay；必要时接入 LSP/编译数据库 |
| 图谱过密 | 分区、聚合、子图、按需展开和五视图切换 |
| 测试环境不一致 | 将测试作为可选质量证据，不阻塞静态图谱生成 |

## 14. 完成定义

Spring Boot 第一版完成时：

- 用户可选择 Java Spring Boot 项目并获得项目侦察报告；
- 可识别 Maven/Gradle、Spring Boot、核心分层、路由、JPA 实体和配置；
- Route → Controller → Service → Repository → Entity 的主链每条边均可回到证据；
- 未验证或未知关系不会伪装为完整框架事实；
- 图谱、Agent 阶段、证据和质量结果可保存、回看、删除；
- 现有 Python 图谱仍可运行；
- TypeScript/NestJS 的接入只需新增 Adapter，不重写 UI、事件或存储契约。
