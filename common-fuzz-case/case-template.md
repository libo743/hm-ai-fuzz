# fuzz 用例总结模板

当需要分析一个新的 Linux 接口并将其接入 `hm-ai-fuzz` 时，按以下模板总结。

## 使用方法

建议按下面顺序填写，不要跳步：

1. 先填接口概述
2. 再填源码证据
3. 再填已确认能力
4. 再填 discover / diff / generate / validate 映射
5. 最后再填代码改动建议

如果“源码证据”一节填不出来，后面几节都不应写成确定结论。

## 最低完成标准

一份可用的用例总结，至少要满足：

- 有明确目标
- 有源码证据
- 有至少一个已确认操作
- 能说明最终写入哪个 `syzkaller` 文件
- 能说明如何验证是否成功

## 1. 接口概述

- 子系统：
- 目标路径或接口名：
- 节点类型：
- 功能简述：

## 2. 源码证据

- 注册文件：
- 注册函数、宏或入口：
- 关联 ops 结构：
- handler 符号：
- 关键源码位置：

## 3. 已确认能力

- 已确认支持的操作：
- 每个操作的源码证据：
- 暂不确认的操作：

## 4. discover 阶段输入输出映射

### 输入

- `kernel_src`
- `target_subsystem`
- `scope_path`
- `semantic_signals`

### 期望输出

- `discover.json` 中的接口项如何表示
- 是否需要 LLM discover 补充
- `metadata` 里要保存什么

## 5. diff 阶段输入输出映射

### 输入

- `discover-merged.json`
- baseline JSON

### 期望输出

- 新增项的唯一 key 如何定义
- 会展开成哪些 `target + op` 项
- 哪些项不应进入差集

## 6. generate 阶段输入输出映射

### 输入

- `diff.json`
- `syzkaller_dir`

### 期望输出

- 是否能复用现有 generator
- open 入口别名如何命名
- fd 资源类型是什么
- 哪些通用操作可以直接映射
- 哪些能力需要扩展 generator
- 最终写入 `syzkaller` 仓库的目标文件是什么
- 如果生成了中间 case JSON，它和最终 syzkaller 描述是什么对应关系

## 7. validate 阶段输入输出映射

### 输入

- `generate.json`
- `syzkaller_dir`
- `make_target`

### 期望输出

- 用什么方式验证
- 可能的失败点是什么
- 失败后如何定位到生成单元
- 如何确认该用例已经满足并入 `syzkaller` 仓库的条件

## 8. 代码改动建议

- extractor 要改什么：
- diff 逻辑要改什么：
- generator 要改什么：
- validator 要改什么：
- 建议新增哪些测试或脚本：
- 最终会改动 `syzkaller` 仓库中的哪个输出文件：

## 9. 风险和待确认项

- 动态路径问题：
- 复杂参数语义问题：
- `ioctl` / `mmap` / 特殊操作问题：
- 当前不建议自动生成的部分：
