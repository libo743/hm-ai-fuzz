# hm-ai-fuzz fuzz用例生成 工作流说明

## 1. 文档目的

这份说明书描述 `hm-ai-fuzz` 当前已经落地的 `/proc` 四步工作流，重点说明：

- 每一步的目标
- 每一步的输入和输出
- 输入输出文件位置
- 每一步的验证方法
- 当前真实运行结果
- 仍待改进的点

过程性的设计推演和实现思路保留在：

- [think.md](think.md)

## 2. 总体设计

当前 `/proc` 流程仍然保持 4 步拆分：

1. `discover`
2. `diff`
3. `generate`
4. `validate`

设计原则：

- 每一步只做一件事
- 步与步之间通过 JSON 交互
- 每一步都可以单独执行和单独验证
- 第 3 步生成与第 4 步编译诊断分离

当前版本里，第 1 步 `discover` 已经演进成内部三段式：

- `discover.json`
  Python/规则基础发现结果
- `discover-llm.json`
  LLM 补充发现结果
- `discover-merged.json`
  供第 2 步真正消费的 discover 权威结果

因此，新设计不是“LLM 只给建议”，而是“LLM 结果先独立落盘，再 merge 后进入 diff”。

## 3. 端到端流程概览

1. 输入 Linux 源码路径和目标模块
2. 第 1 步先执行 `discover`
3. `discover` 内部再拆成 Python/规则发现、LLM discover 补充、merge discover
4. 第 2 步基于 merged discover 输出新增接口项
5. 第 3 步输出 syzkaller 描述文件和生成元数据
6. 第 4 步执行 `make descriptions` 并输出诊断

当前工作流有两条并行输出视图：

- 现有运行视图：
  `discover / discover_llm / discover_merged / diff / generate / validate`
- v2 统一协议视图：
  `discover_v2 / discover_llm_v2 / discover_merged_v2 / diff_v2 / generate_v2 / validate_v2`

其中 v2 视图不是静态转写，已经能真实执行到生成和编译验证。

当前两套视图的定位是：

- `v1` 继续保留，作为当前 `/proc` 主流程的兼容视图和回归基线
- `v2` 作为后续跨模块统一协议和新模块接入标准

当前默认文件链路：

- 第 1 步：
  [discover.json](../out/discover.json)
  [discover-llm.json](../out/discover-llm.json)
  [discover-merged.json](../out/discover-merged.json)
  [discover-v2.json](../out/discover-v2.json)
  [discover-llm-v2.json](../out/discover-llm-v2.json)
  [discover-merged-v2.json](../out/discover-merged-v2.json)
- 第 2 步：
  [diff.json](../out/diff.json)
  [diff-v2.json](../out/diff-v2.json)
- 第 3 步：
  [generate.json](../out/generate.json)
  [generate-v2.json](../out/generate-v2.json)
  `../syzkaller/sys/linux/proc_auto.txt`
  `../syzkaller/sys/linux/proc_auto.txt.const`
- 第 4 步：
  [validate.json](../out/validate.json)
  [validate-v2.json](../out/validate-v2.json)
- 总汇总：
  [workflow-result.json](../out/workflow-result.json)

默认外部仓相对路径约定：

- 当前仓库：`.`
- Linux 源码：`../linux`
- syzkaller 源码：`../syzkaller`

当前建议的输出目录约定：

- `../out/`
  主流程默认输出目录
- `../out/scenarios/`
  各种验证脚本或故障注入场景的输出目录

说明：

- `out/` 根目录保存主流程标准产物
- `out/scenarios/` 保存故障注入、抽样验证、LLM 小样本联调等场景化结果

## 4. 第一步：Discover

### 4.1 目标

从 Linux 源码中定位目标模块下的 `/proc` 节点，并抽取接口能力集合。

当前主要识别：

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

### 4.2 实现位置

- 代码：
  [extractor.py](../extractors/proc/extractor.py)
- 验证脚本：
  [validate_proc_discover.sh](../scripts/validate_proc_discover.sh)

### 4.3 输入

- `kernel_src`
- `target_module`
- `search_method`
- `scan_mode`

### 4.4 输出

输出为 `discover.json`，表示 Python/规则发现结果；每项是一个统一的 `InterfaceSpec`：

- `subsystem`
- `target`
- `kind`
- `capabilities`
- `source`
- `metadata`

如果启用 LLM discover，还会额外输出：

- `discover-llm.json`
  只包含 LLM 补充发现的操作/节点
- `discover-merged.json`
  供第 2 步真正消费的 merged discover 结果

同时还会输出对应的 v2 视图：

- `discover-v2.json`
- `discover-llm-v2.json`
- `discover-merged-v2.json`

### 4.5 验证方法

```bash
cd ./hm-ai-fuzz
bash scripts/validate_proc_discover.sh
```

无依赖测试入口：

```bash
cd ./hm-ai-fuzz
bash scripts/run_proc_test_suite.sh
```

## 5. 第二步：Diff

### 5.1 目标

先把 `discover.json` 和 `discover-llm.json` 合并成 `discover-merged.json`，再把 merged 结果展开成 `subsystem:target:op` 级别的接口项，与 baseline 做差。若 baseline 是空 JSON，则所有接口项都视为新增。

### 5.2 实现位置

- 代码：
  [simple_diff.py](../modelers/simple_diff.py)
- demo 脚本：
  [run_proc_diff_demo.sh](../scripts/run_proc_diff_demo.sh)
- 抽样验证脚本：
  [validate_proc_diff_with_sampled_base.sh](../scripts/validate_proc_diff_with_sampled_base.sh)

### 5.3 输入

- `discover-merged.json`
- baseline JSON

### 5.4 输出

输出为 `diff.json`，其中关键字段：

- `current`
- `existing_keys`
- `new`
- `new_items`

`new_items` 是第 3 步真正消费的新增接口项。
当前 `/proc` 流程里，这些新增项来自 `discover-merged.json`，不是只来自 base discover。

同时还会输出 `diff-v2.json`，把新增项表示成统一的：

- `item_key`
- `interface_id`
- `operation`
- `syscall_bindings`

### 5.5 验证方法

空 baseline：

```bash
cd ./hm-ai-fuzz
bash scripts/run_proc_diff_demo.sh
```

抽样 baseline：

```bash
cd ./hm-ai-fuzz
bash scripts/validate_proc_diff_with_sampled_base.sh
```

## 6. 第三步：Generate

### 6.1 目标

把 `diff.json` 里的 `new_items` 生成成 syzkaller 可编译的最小描述文件。

当前最小策略：

- 支持 `open/read/write/lseek/getdents64/ioctl/mmap/poll`
- 输出 `proc_auto.txt` 和 `proc_auto.txt.const`
- 文件节点生成 `openat$proc_*` 及对应 `read/write/lseek/ioctl/mmap/poll`
- 目录节点生成 `openat$proc_*`，并复用通用 `getdents64`

### 6.2 实现位置

- 代码：
  [minimal.py](../generators/syzkaller/minimal.py)
- demo 脚本：
  [run_proc_generate_demo.sh](../scripts/run_proc_generate_demo.sh)
- 验证脚本：
  [validate_proc_generate.sh](../scripts/validate_proc_generate.sh)

### 6.3 输入

- `diff.json`
- syzkaller 仓库根目录

### 6.4 输出

- `generate.json`
- `generate-v2.json`
- `../syzkaller/sys/linux/proc_auto.txt`
- `../syzkaller/sys/linux/proc_auto.txt.const`

其中 `generate-v2.json` 会记录：

- `generated_files`
- `generated_units`
- `skipped_items`
- `summary`

### 6.5 验证方法

```bash
cd ./hm-ai-fuzz
bash scripts/validate_proc_generate.sh
```

## 7. 第四步：Validate

### 7.1 目标

在 syzkaller 目录执行 `make descriptions`，验证第 3 步生成结果是否可编译，并提取诊断。

### 7.2 实现位置

- 代码：
  [syzkaller_build.py](../validators/syzkaller_build.py)
- demo 脚本：
  [run_proc_validate_demo.sh](../scripts/run_proc_validate_demo.sh)

### 7.3 输入

- `generate.json`
- syzkaller 仓库根目录
- `make_target`
- `timeout_sec`

### 7.4 输出

输出为 `validate.json`，主要字段：

- `status`
- `diagnostics`
- `metadata`

同时还会输出 `validate-v2.json`，用于统一表示：

- `status`
- `diagnostics`
- `summary`
- `metadata`

### 7.5 验证方法

```bash
cd ./hm-ai-fuzz
bash scripts/run_proc_validate_demo.sh
```

## 8. 当前真实结果

在 `../linux` 和 `../syzkaller` 上，当前真实结果是：

- 第 1 步发现 `29` 个 `/proc` 节点
- 第 2 步对空 baseline 展开得到 `66` 个新增接口项
- 第 3 步生成 `proc_auto.txt` 与 `proc_auto.txt.const`
- 第 4 步 `make descriptions` 通过
- v2 四步结果也已同时产出并通过编译验证

当前还补充验证过一条 LLM smoke 路径：

- 开启 LLM discover 后，`discover-llm.json` 可产生额外操作
- 这些操作会进入 `discover-merged.json`
- `diff.json` 的新增接口项数量会真实变化
- 生成和 `make descriptions` 仍可通过
- 已验证示例中，`/proc/consoles` 的 `lseek` 由 LLM discover 补充进入 merged，再进入 diff 和生成链路

## 9. v2 协议说明

当前仓库已经提供一套面向全模块的统一 schema 草案，目录见：

- [schema/README.md](../schema/README.md)

用于统一约束：

- `discover_v2 / discover_llm_v2 / discover_merged_v2`
- `diff_v2`
- `generate_v2`
- `validate_v2`

## 10. 待改进点

- 第 1 步对复杂宏、间接注册和配置依赖节点仍可能漏检
- 第 2 步当前只按 `target + op` 去重，还没有建模参数差异
- 第 3 步还只是最小模板生成，尚未覆盖复杂 syscall 语义
- 第 4 步还没有自动修复环路，只做编译与错误提取
