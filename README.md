# hm-ai-fuzz

`hm-ai-fuzz` 是一个面向 Linux 接口发现、差集、syzkaller 描述生成与验证的插件化框架。

当前目标：

1. 用统一的数据模型承接不同子系统的接口发现结果。
2. 保留 4 步通用流程：
   - discover
   - diff
   - generate
   - validate
3. 把 `/proc` 作为第一个插件化子系统。
4. 为后续扩展到 `/dev`、netlink、其他 syscall family 留出稳定框架。

当前已经落地一条可运行的 `/proc` 主流程：

1. 第 1 步从 Linux 源码里扫描 `fs/proc`，识别 `/proc` 节点及其 `open/read/write/lseek/getdents64` 等能力。
2. 第 2 步把发现结果拍平为接口项，并与已有基线做差集。
3. 第 3 步把新增接口生成到 `syzkaller/sys/linux/proc_auto.txt` 和 `proc_auto.txt.const`。
4. 第 4 步在 syzkaller 目录执行 `make descriptions`，检查生成描述是否可编译。

## 目录

```text
core/                 # 通用 schema、pipeline、协议
extractors/proc/      # /proc 子系统发现插件
modelers/             # 统一模型转换层
generators/syzkaller/ # syzkaller 描述生成层
validators/           # 编译/诊断层
workflows/            # 顶层 workflow 入口
scripts/              # 验证脚本
```

## 输入

- `--kernel-src`
  Linux 源码路径，例如 `/home/libo/work/linux`
- `--syzkaller-dir`
  syzkaller 仓库路径，例如 `/home/libo/work/syzkaller`
- `--target-module`
  当前默认为 `fs/proc`
- `--existing-json`
  可选基线 JSON；demo 阶段不传时等价于与空基线比较

## 输出

默认输出目录为 `out/`，其中：

- `out/discover.json`
  第 1 步发现结果
- `out/diff.json`
  第 2 步差集结果，`new_items` 是新增接口项
- `out/generate.json`
  第 3 步生成结果，记录生成文件和生成单元
- `out/validate.json`
  第 4 步编译验证结果
- `out/workflow-result.json`
  四步总汇总

syzkaller 侧产物：

- `/home/libo/work/syzkaller/sys/linux/proc_auto.txt`
- `/home/libo/work/syzkaller/sys/linux/proc_auto.txt.const`

## 运行

```bash
cd /home/libo/work/hm-ai-fuzz
python3 -m workflows.proc_workflow --help
```

完整跑一遍：

```bash
cd /home/libo/work/hm-ai-fuzz
python3 -m workflows.proc_workflow \
  --workspace /home/libo/work/hm-ai-fuzz \
  --kernel-src /home/libo/work/linux \
  --syzkaller-dir /home/libo/work/syzkaller \
  --out-dir /home/libo/work/hm-ai-fuzz/out \
  --out-json /home/libo/work/hm-ai-fuzz/out/workflow-result.json
```

或者直接跑验证脚本：

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/validate_proc_workflow.sh
```

如果环境里没有 `pytest`，可以直接跑内置无依赖测试：

```bash
cd /home/libo/work/hm-ai-fuzz
bash scripts/run_proc_test_suite.sh
```

## 当前状态

- `/proc` 发现逻辑基于真实 Linux 源码扫描，不是占位数据。
- 差集逻辑已经能把发现结果按 `subsystem:target:op` 维度展开。
- syzkaller 生成逻辑已经会写入 `.txt` 和 `.txt.const`。
- 编译验证逻辑已经会执行 `make descriptions` 并提取诊断。

## 后续扩展方向

- 把 `/proc` 之外的子系统实现为新的 extractor/modeler/generator/validator 组合。
- 把第 3 步从最小描述生成扩展到更多 syscall 模式和参数模板。
- 把第 4 步从单次编译扩展到更细粒度的失败归因与自动修复回路。
