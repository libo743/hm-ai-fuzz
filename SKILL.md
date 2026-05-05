---
name: hm-ai-fuzz
description: 指导大模型在 hm-ai-fuzz 项目中基于 Linux 源码发现接口、总结 fuzz 用例、补充 syzkaller 描述生成，并按照项目现有 discover、diff、generate、validate 流程产出结构化结果。
---

# hm-ai-fuzz 技能说明

## 适用场景

当任务属于以下类型时，遵循本技能说明：

- 分析 Linux 某个子系统是否可以新增 fuzz 用例
- 从 Linux 源码中发现新的接口节点或操作能力
- 将发现结果补充到当前工作流
- 为某个子系统新增 discover / diff / generate / validate 支持
- 总结一个新的 fuzz 用例并说明如何接入项目
- 为现有 syzkaller 生成结果补充建模建议或修复建议

## 项目目标

本项目是一个面向 Linux 接口发现、差集分析、syzkaller 描述生成与验证的框架。

当前已实现 `/proc` 子系统的完整流程：

1. `discover`
2. `diff`
3. `generate`
4. `validate`

主流程入口：

- `workflows/proc_workflow.py`

当前项目的工作方式不是“完全由大模型自由生成 fuzz 用例”，而是：

- Python / 规则逻辑负责主干流程
- 大模型负责补充发现、建模建议、修复建议
- 最终结果应尽量落回项目代码、JSON 产物和 syzkaller 输出文件
- 新增的 fuzz 用例最终必须能够写入外部 `syzkaller` 仓库并通过验证，而不只是停留在本仓库内部的 JSON case

## 工作原则

### 1. 先读现有实现，再扩展

开始工作前，优先阅读：

- `README.md`
- `workflows/proc_workflow.py`
- 对应子系统的 `extractors/`
- `modelers/`
- `generators/syzkaller/`
- `validators/`

不要脱离现有结构另起一套流程。

### 2. 以源码证据驱动

所有 fuzz 用例发现和操作能力判断，都应以 Linux 源码中的明确证据为基础，例如：

- 注册函数
- 注册宏
- 路径解析逻辑
- `proc_ops`
- `file_operations`
- `seq_operations`
- handler 函数

如果证据不足，应明确标记为待确认，而不是强行写入最终结果。

### 3. 输出必须对齐项目已有步骤

本项目所有新增用例分析，优先按已有四步流程组织输出：

1. `discover`
2. `diff`
3. `generate`
4. `validate`

每一步都要明确：

- 输入是什么
- 输出是什么
- 对应代码在哪
- 新增模块时要改哪里

### 4. 优先复用现有生成能力

当前 syzkaller 最小生成器主要支持以下操作：

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

新增用例时，先判断能否映射到上述能力集。
如果不能，应先输出“生成器需要扩展的点”，而不是直接假设已经支持。

### 5. 最终交付必须是可发布到 syzkaller 的产物

本项目里“新增 fuzz 用例”的最终含义不是只新增分析结果或本地 case JSON，而是至少满足以下链路：

1. 在 `discover` 中被发现
2. 在 `diff` 中形成新增接口项
3. 在 `generate` 中转换成可写入 `syzkaller` 仓库的描述
4. 在 `validate` 中通过 `make descriptions` 或等价验证

允许存在中间辅助产物，例如：

- `out/cases/proc/*.json`
- 发现阶段或建模阶段的建议 JSON

但这些都不是最终目标。最终目标仍然是：

- `../syzkaller/sys/linux/*.txt`
- `../syzkaller/sys/linux/*.txt.const`
- 对应的 `validate.json` / `publish.json`

## 建议推导顺序

能力较弱的模型不要直接从“我要新增 fuzz 用例”跳到“修改 generator”。应按下面顺序推导：

1. 先确认目标接口是否真实存在于 Linux 源码中
2. 再确认它属于哪个子系统、路径或目标对象是什么
3. 再确认它支持哪些操作
4. 再判断这些操作能否映射到当前 generator
5. 再决定需要改 discover、diff、generate、validate 中的哪一步
6. 最后才修改代码并验证是否真的进入 `syzkaller` 仓库

如果某一步证据不足，就停在那一步，输出“待确认项”，不要直接跳过。

## 最小成功路径

对新增用例，优先追求最小成功路径，而不是一次做复杂建模。

一个最小成功路径通常是：

1. 选择一个证据最充分的接口
2. 至少确认 `open`，如果是普通只读文件，再确认 `read`
3. 让它先进入 `discover.json`
4. 让它在 `diff.json` 中形成新增项
5. 让它进入 `../syzkaller/sys/linux/*.txt`
6. 让 `make descriptions` 通过

在最小成功路径跑通前，不优先处理这些复杂能力：

- 复杂 `ioctl`
- 复杂 `mmap`
- 动态路径
- 参数语义不明的写操作

## 操作步骤清单

如果任务是“为某个接口新增 fuzz 用例”，按下面清单逐项执行。

### 步骤 1：确认目标

先回答：

- 目标子系统是什么
- 目标路径或接口名是什么
- 这是文件、目录、符号链接还是动态节点

如果这一步都无法回答，不要进入后续生成阶段。

### 步骤 2：收集源码证据

至少找到：

- 注册文件
- 注册函数、宏或入口
- 对应 ops 结构或 handler
- 关键源码位置

如果只知道路径，不知道注册点或 ops，不足以进入最终生成。

### 步骤 3：确认支持操作

优先确认以下操作：

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

确认规则：

- 有直接源码证据才记为“已确认”
- 没有证据但模式上可能存在的，只能记为“待确认”

### 步骤 4：判断能否进入当前 generator

把上一步得到的操作与当前 generator 能力比较：

- 如果都是已支持能力，优先复用现有 generator
- 如果包含未支持能力，先只生成已支持部分
- 如果核心能力都不在现有 generator 支持范围内，先输出 generator 扩展点，不要伪造可运行用例

### 步骤 5：映射到四步流程

必须明确：

- discover 阶段新增什么
- diff 阶段新增项如何展开
- generate 阶段写入哪个 `syzkaller` 目标文件
- validate 阶段用什么方式确认成功

### 步骤 6：定义最终成功标准

只有同时满足下面条件，才算“新增用例成功”：

1. 发现结果进入 `discover` 输出
2. 新增项进入 `diff` 输出
3. 描述进入 `../syzkaller/sys/linux/*.txt`
4. `validate.status == passed`

如果只生成了本仓库内 JSON case，不算最终成功。

## 判断分支

### 分支 A：只有路径，没有源码证据

处理方式：

- 不进入 generate
- 输出待确认项
- 继续找注册点和 ops

### 分支 B：有注册点，但操作集合不完整

处理方式：

- 只使用已确认操作进入 discover / diff / generate
- 不确认的操作保留到 notes 或 TODO

### 分支 C：操作已确认，但 generator 不支持

处理方式：

- 先描述 generator 扩展点
- 明确需要新增哪种资源、别名或 syscall 映射
- 不要假装该能力已经成功接入

### 分支 D：描述已生成，但 validate 失败

处理方式：

- 看失败单元和报错
- 判断是语法问题、资源建模问题，还是参数类型问题
- 优先做最小修复，重新验证

## 失败回退规则

如果一次任务无法完整跑通，按下面优先级回退：

1. 保留 discover 成果
2. 保留 diff 粒度设计
3. 缩小 generate 范围，只保留最小可支持操作
4. 把复杂能力转成 TODO，而不是让整个新增流程失败

回退后仍要明确说明：

- 当前已经完成到哪一步
- 卡在哪一步
- 需要补什么证据或代码

## 四步流程与输入输出

以下输入输出必须作为分析和实现的基准，尽量与项目现有实现保持一致。

### 第一步：Discover

#### 目标

从 Linux 源码中发现目标子系统下的可 fuzz 接口，并抽取接口能力集合。

#### 主要输入

- `kernel_src`
  Linux 源码根目录
- `target_subsystem`
  语义目标，例如 `proc`
- `scope_path`
  可选路径范围，例如 `fs/proc`
- `semantic_signals`
  可选语义信号，例如注册函数、关键结构体、关键宏
- `search_method`
  搜索方式，如 `exact` / `prefix` / `substring`
- `scan_mode`
  扫描方式，如 `auto` / `full`

#### 主要输出

现有输出包括：

- `discover.json`
  Python / 规则发现结果
- `discover-llm.json`
  LLM 补充发现结果
- `discover-merged.json`
  merge 后的 discover 权威结果

以及对应 v2 视图：

- `discover-v2.json`
- `discover-llm-v2.json`
- `discover-merged-v2.json`

#### 结果要求

每个发现项应尽量对齐统一接口描述，至少包含：

- `subsystem`
- `target`
- `kind`
- `capabilities`
- `source`
- `metadata`

#### 对应代码

- `workflows/proc_workflow.py`
- `extractors/proc/extractor.py`

#### 新增模块时的任务

如果要支持新的子系统，应优先补充：

- 新的 extractor
- 新的注册点定位逻辑
- 新的能力识别逻辑
- 必要的 metadata 字段

### 第二步：Diff

#### 目标

将 discover 结果与 baseline 做差集，识别新增接口项。

#### 主要输入

- `discover-merged.json`
  merge 后 discover 结果
- baseline JSON
  已有接口基线；如果为空，则所有项视为新增

#### 主要输出

- `diff.json`
- `diff-v2.json`

#### 结果要求

差集结果至少应能回答：

- 当前发现了哪些接口项
- baseline 已有哪些项
- 哪些项是新增项
- 新增项分别对应哪些 `target + op`
- 哪些新增项理论上可以继续进入 syzkaller 生成阶段

#### 对应代码

- `modelers/simple_diff.py`
- `workflows/proc_workflow.py`

#### 新增模块时的任务

如果新模块的差集粒度与 `/proc` 不同，应明确：

- 用什么 key 表示唯一接口项
- 是按路径差分、按操作差分，还是按命令/属性差分
- baseline 应该如何表示

### 第三步：Generate

#### 目标

把差集结果转换成 syzkaller 可消费的描述文件和生成元数据。

#### 主要输入

- `diff.json`
  差集输出
- `syzkaller_dir`
  外部 syzkaller 源码目录

#### 主要输出

- `generate.json`
- `generate-v2.json`
- `../syzkaller/sys/linux/proc_auto.txt`
- `../syzkaller/sys/linux/proc_auto.txt.const`
- 可选的中间 case 产物，例如 `out/cases/proc/*.json`

#### 结果要求

生成阶段至少应明确：

- 哪些新增接口被成功映射成 syzkaller 描述
- 哪些接口因为能力不足或语义不清被跳过
- 输出文件路径
- 生成的单位数量和跳过数量
- 哪些中间 case 只是辅助信息，哪些内容已经真正进入 `syzkaller` 仓库产物

#### 对应代码

- `generators/syzkaller/minimal.py`
- `workflows/proc_workflow.py`

#### 新增模块时的任务

如果要支持新的模块或新的接口语义，应明确：

- 现有 generator 是否足够
- 需要新增哪些操作映射
- 是否需要新的资源类型
- 是否需要新的 open 别名或专用 syscall 变体
- 是否需要新的 `.txt` 或 `.const` 产物
- 生成后的结果最终写入 `syzkaller` 仓库的哪个文件

### 第四步：Validate

#### 目标

把生成的 syzkaller 描述写入外部仓库，并通过构建或描述检查验证其有效性。

#### 主要输入

- 第三步生成结果
- `syzkaller_dir`
- `make_target`
  当前默认是 `descriptions`

#### 主要输出

- `validate.json`
- `validate-v2.json`
- `publish.json`

#### 结果要求

验证阶段至少应明确：

- 构建是否成功
- 失败发生在哪个生成单元
- 错误信息是什么
- 是否生成了可供后续修复的线索
- 新增用例是否已经满足“可并入 syzkaller 仓库”的最低条件

#### 对应代码

- `validators/syzkaller_build.py`
- `workflows/proc_workflow.py`

#### 新增模块时的任务

如果新模块引入了不同的验证要求，应明确：

- 是否仍复用 `make descriptions`
- 是否需要新的验证脚本
- 是否需要补充失败诊断和自动修复建议逻辑

## 如何总结一个 fuzz 用例

当分析一个新接口时，必须至少输出以下内容。

### 1. 接口概述

- 子系统
- 目标路径或接口名
- 节点类型
- 功能简述

### 2. 源码证据

- 注册文件
- 注册函数、宏或入口
- 关联 ops 结构
- handler 符号
- 关键源码位置

### 3. 已确认能力

- 已确认支持的操作
- 每个操作对应的源码证据
- 暂不确认的操作

### 4. 对应工作流位置

- 这个接口在 discover 阶段应该如何表示
- 在 diff 阶段会展开成哪些新增项
- 在 generate 阶段能否映射到现有 syzkaller 描述
- 最终会写入 `syzkaller` 仓库的哪个目标文件
- 在 validate 阶段可能遇到什么问题

### 5. 代码改动建议

- extractor 要改什么
- diff 逻辑是否要改
- generator 要改什么
- validator 是否要改
- 是否需要新增测试或脚本

## 分析新增模块时的输出格式

当任务是“为其他模块新增用例”时，建议按下面结构输出：

### 一、模块概述

- 模块名称
- 典型注册模式
- 可识别的接口对象
- 与 `/proc` 的相似点和差异点

### 二、四步输入输出映射

- discover 的输入输出如何定义
- diff 的输入输出如何定义
- generate 的输入输出如何定义
- validate 的输入输出如何定义

### 三、最小可行用例

- 先挑一个证据最充分的接口
- 总结成一个保守 fuzz 用例
- 判断是否能直接复用现有 generator
- 明确该用例最终如何落到 `../syzkaller/sys/linux/*.txt`

### 四、代码接入点

- 需要新增或修改哪些模块
- 哪些部分可复用 `/proc`
- 哪些部分必须新建实现

## 禁止事项

- 不要脱离当前项目的四步流程
- 不要在没有源码证据的情况下臆造能力集合
- 不要把复杂 ioctl、mmap、动态路径直接当作已支持
- 不要只输出概念性建议而不给出对应步骤输入输出
- 不要只给自然语言分析，不落到 discover / diff / generate / validate 其中的某一步
- 不要把仅存在于本仓库内部 JSON case 的结果当作最终完成；必须说明如何进入 `syzkaller` 仓库
