# hm-ai-fuzz `/proc` 工作流说明

## 1. 文档目的

这份说明书描述 `hm-ai-fuzz` 当前已经落地的 `/proc` 四步工作流，重点说明：

- 每一步的目标
- 每一步的输入和输出
- 输入输出文件位置
- 每一步的验证方法
- 当前真实运行结果
- 仍待改进的点

过程性的设计推演和实现思路保留在：

- [think.md](/home/libo/work/hm-ai-fuzz/workflow/think.md)

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

## 3. 端到端流程概览

1. 输入 Linux 源码路径和目标模块
2. 第 1 步输出 `/proc` 节点发现结果
3. 第 2 步输出新增接口项
4. 第 3 步输出 syzkaller 描述文件和生成元数据
5. 第 4 步执行 `make descriptions` 并输出诊断

当前默认文件链路：

- 第 1 步：
  [discover.json](/home/libo/work/hm-ai-fuzz/out/discover.json)
- 第 2 步：
  [diff.json](/home/libo/work/hm-ai-fuzz/out/diff.json)
- 第 3 步：
  [generate.json](/home/libo/work/hm-ai-fuzz/out/generate.json)
  [proc_auto.txt](/home/libo/work/syzkaller/sys/linux/proc_auto.txt)
  [proc_auto.txt.const](/home/libo/work/syzkaller/sys/linux/proc_auto.txt.const)
- 第 4 步：
  [validate.json](/home/libo/work/hm-ai-fuzz/out/validate.json)
- 总汇总：
  [workflow-result.json](/home/libo/work/hm-ai-fuzz/out/workflow-result.json)

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

### 4.2 实现位置

- 代码：
  [extractor.py](/home/libo/work/hm-ai-fuzz/extractors/proc/extractor.py)
- 验证脚本：
  [validate_proc_discover.sh](/home/libo/work/hm-ai-fuzz/scripts/validate_proc_discover.sh)

### 4.3 输入

- `kernel_src`
- `target_module`
- `search_method`
- `scan_mode`

### 4.4 输出

输出为 `discover.json`，每项是一个统一的 `InterfaceSpec`：

- `subsystem`
- `target`
- `kind`
- `capabilities`
- `source`
- `metadata`

### 4.5 验证方法

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/validate_proc_discover.sh
```

无依赖测试入口：

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/run_proc_test_suite.sh
```

## 5. 第二步：Diff

### 5.1 目标

把第 1 步发现结果展开成 `subsystem:target:op` 级别的接口项，再与 baseline 做差。

demo 阶段如果 baseline 是空 JSON，则所有接口项都视为新增。

### 5.2 实现位置

- 代码：
  [simple_diff.py](/home/libo/work/hm-ai-fuzz/modelers/simple_diff.py)
- demo 脚本：
  [run_proc_diff_demo.sh](/home/libo/work/hm-ai-fuzz/scripts/run_proc_diff_demo.sh)
- 抽样验证脚本：
  [validate_proc_diff_with_sampled_base.sh](/home/libo/work/hm-ai-fuzz/scripts/validate_proc_diff_with_sampled_base.sh)

### 5.3 输入

- `discover.json`
- baseline JSON

### 5.4 输出

输出为 `diff.json`，其中关键字段：

- `current`
- `existing_keys`
- `new`
- `new_items`

`new_items` 是第 3 步真正消费的新增接口项。

### 5.5 验证方法

空 baseline：

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/run_proc_diff_demo.sh
```

抽样 baseline：

```bash
cd /home/libo/work/hm-ai-fuzz
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
  [minimal.py](/home/libo/work/hm-ai-fuzz/generators/syzkaller/minimal.py)
- demo 脚本：
  [run_proc_generate_demo.sh](/home/libo/work/hm-ai-fuzz/scripts/run_proc_generate_demo.sh)
- 验证脚本：
  [validate_proc_generate.sh](/home/libo/work/hm-ai-fuzz/scripts/validate_proc_generate.sh)

### 6.3 输入

- `diff.json`
- syzkaller 仓库根目录

### 6.4 输出

- `generate.json`
- `/home/libo/work/syzkaller/sys/linux/proc_auto.txt`
- `/home/libo/work/syzkaller/sys/linux/proc_auto.txt.const`

### 6.5 验证方法

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/validate_proc_generate.sh
```

## 7. 第四步：Validate

### 7.1 目标

在 syzkaller 目录执行 `make descriptions`，验证第 3 步生成结果是否可编译，并提取诊断。

### 7.2 实现位置

- 代码：
  [syzkaller_build.py](/home/libo/work/hm-ai-fuzz/validators/syzkaller_build.py)
- demo 脚本：
  [run_proc_validate_demo.sh](/home/libo/work/hm-ai-fuzz/scripts/run_proc_validate_demo.sh)

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

### 7.5 验证方法

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/run_proc_validate_demo.sh
```

## 8. 当前真实结果

在 `/home/libo/work/linux` 和 `/home/libo/work/syzkaller` 上，当前真实结果是：

- 第 1 步发现 `29` 个 `/proc` 节点
- 第 2 步对空 baseline 展开得到 `66` 个新增接口项
- 第 3 步生成 `proc_auto.txt` 与 `proc_auto.txt.const`
- 第 4 步 `make descriptions` 通过

## 9. 待改进点

- 第 1 步对复杂宏、间接注册和配置依赖节点仍可能漏检
- 第 2 步当前只按 `target + op` 去重，还没有建模参数差异
- 第 3 步还只是最小模板生成，尚未覆盖复杂 syscall 语义
- 第 4 步还没有自动修复环路，只做编译与错误提取
