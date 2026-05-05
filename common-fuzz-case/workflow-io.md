# 四步工作流输入输出总表

本文件用于总结 `hm-ai-fuzz` 当前已实现工作流的输入输出，供新增模块时复用。

## 使用顺序

能力较弱的模型建议严格按下面顺序使用本文件：

1. 先看 Discover，确认接口是否真实存在
2. 再看 Diff，确认新增项粒度
3. 再看 Generate，确认是否能进入 `syzkaller`
4. 最后看 Validate，确认如何证明接入成功

不要先看 Generate 再倒推 Discover。

## 最小检查清单

在进入下一步前，先检查当前步是否满足最低条件：

- Discover：是否已有目标、来源、能力集合
- Diff：是否已有稳定唯一 key 和新增项
- Generate：是否已有可落盘到 `syzkaller` 的映射
- Validate：是否已有明确的验证命令和成功标准

## 1. Discover

### 目标

从 Linux 源码中发现接口对象，并提取可确认的能力集合。

### 当前实现参考

- `workflows/proc_workflow.py`
- `extractors/proc/extractor.py`

### 输入

- `kernel_src`
- `target_subsystem`
- `scope_path`
- `semantic_signals`
- `search_method`
- `scan_mode`

### 输出

- `discover.json`
- `discover-llm.json`
- `discover-merged.json`
- `discover-v2.json`
- `discover-llm-v2.json`
- `discover-merged-v2.json`

### 输出项最低要求

- `subsystem`
- `target`
- `kind`
- `capabilities`
- `source`
- `metadata`

### 新模块迁移时要回答的问题

- 目标对象是什么
- 注册点在哪里
- 如何解析路径或标识符
- 如何确认支持操作
- `metadata` 里需要保留哪些子系统特有字段

## 2. Diff

### 目标

将 discover 的权威结果与 baseline 做差集，筛出新增项。

### 当前实现参考

- `modelers/simple_diff.py`
- `workflows/proc_workflow.py`

### 输入

- `discover-merged.json`
- baseline JSON

### 输出

- `diff.json`
- `diff-v2.json`

### 输出项最低要求

- 当前接口全集
- baseline 接口全集
- 新增接口项
- 新增项展开后的最小粒度

### 新模块迁移时要回答的问题

- 唯一标识如何定义
- 差集是按路径、按操作，还是按更细粒度对象
- baseline 应保存什么格式

## 3. Generate

### 目标

将新增接口项映射成 syzkaller 描述和生成元数据，并把最终可用用例写入外部 `syzkaller` 仓库目标文件。

### 当前实现参考

- `generators/syzkaller/minimal.py`
- `workflows/proc_workflow.py`

### 输入

- `diff.json`
- `syzkaller_dir`

### 输出

- `generate.json`
- `generate-v2.json`
- `../syzkaller/sys/linux/proc_auto.txt`
- `../syzkaller/sys/linux/proc_auto.txt.const`
- 可选的中间 case 产物，例如 `out/cases/proc/*.json`

### 当前最小生成能力

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

### 新模块迁移时要回答的问题

- 能否复用现有最小能力映射
- 是否需要新的资源类型
- 是否需要新的 syscall 别名
- 是否需要新的 `.const` 内容
- 哪些接口应跳过而不是强行生成
- 最终产物写入 `syzkaller` 仓库的哪个文件
- 中间 case 产物和最终 syzkaller 产物之间如何对应

## 4. Validate

### 目标

验证生成后的 syzkaller 描述是否可以被外部 syzkaller 仓库接受，并确认新增用例已经具备并入仓库的条件。

### 当前实现参考

- `validators/syzkaller_build.py`
- `workflows/proc_workflow.py`

### 输入

- 第三步生成结果
- `syzkaller_dir`
- `make_target`

### 输出

- `validate.json`
- `validate-v2.json`
- `publish.json`

### 新模块迁移时要回答的问题

- 是否继续使用 `make descriptions`
- 是否需要模块专属验证脚本
- 如何定位失败单元
- 如何给后续修复提供足够诊断
- 如何证明新增用例已经真正进入 `syzkaller` 仓库产物而不是只存在于本仓库中
