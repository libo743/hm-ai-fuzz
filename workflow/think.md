# hm-ai-fuzz Workflow Notes

## 目标

这套流程的目标是把 Linux `/proc` 相关静态分析逐步转成 syzkaller 可消费的 fuzz 描述，并且保留后续扩展到其他 syscall family 的架构空间。

这里记录的是两类内容：

- 如何把 `/proc` 节点变成可新增的 fuzz 用例
- 为什么整体流程拆成 4 步，而不是做成一个大而全的单体

## 整体流程思考

关于 `/proc` fuzz 用例新增，比较稳定的做法不是直接让一个模块同时负责“理解源码”“判断新增”“生成描述”“编译修复”，而是拆成 4 步：

1. `discover`
2. `diff`
3. `generate`
4. `validate`

这样拆的原因：

- 第 1 步是源码发现问题
- 第 2 步是集合差集问题
- 第 3 步是 syzkaller 描述生成问题
- 第 4 步是工具链编译和诊断问题

这四类问题的失败模式不同，拆开以后更容易：

- 单独验证
- 单独回放
- 单独替换实现
- 在第 3 步和第 4 步之间形成明确的文件接口

## 为什么新增 `/proc` fuzz 用例不能一步完成

新增 `/proc` fuzz 用例表面上看只是“生成一个 `.txt`”，但实际至少涉及这几层信息：

- Linux 源码里到底注册了哪些 `/proc` 节点
- 每个节点支持哪些 file operation
- 哪些接口在当前 baseline 里已经有覆盖
- 哪些新增接口能映射成 syzkaller 可接受的描述
- 生成后的描述是否能通过 `make descriptions`

所以更稳妥的思路是先把“发现”和“生成”解耦，再把“生成”和“编译验证”解耦。

## 第一步：发现 `/proc` 节点和操作能力

这一层的目标是从 Linux 源码中找出：

- `/proc` 路径
- 节点类型
- 支持的操作集合

当前关注的操作包括：

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

实现重点：

- 先建立源码索引
- 识别 `proc_create`、`proc_create_seq`、`proc_mkdir`、`proc_symlink` 等注册模式
- 解析对应的 `proc_ops` / `file_operations`
- 在符号无法完全解开的情况下允许保守回退

保守回退的意义：

- 保证流程不断
- 即使某些 ops 符号没完全解析，也至少还能得到一份可用的最小接口清单

这一层对应代码：

- [extractor.py](../extractors/proc/extractor.py)
- [source_index.py](../extractors/proc/source_index.py)
- [locator.py](../extractors/proc/locator.py)
- [ops.py](../extractors/proc/ops.py)

## 第二步：把发现结果转换成“新增接口项”

这一层的关键判断是：

- 第 1 步输出的是“节点”
- 第 3 步需要消费的是“接口项”

所以需要把每个节点的 `supported_ops` 展开成粒度更细的项，例如：

- `/proc/cpuinfo + open`
- `/proc/cpuinfo + read`
- `/proc/cpuinfo + lseek`

再与 baseline 做差。

这里采用的差集键是：

- `subsystem:target:op`

这样做的优点：

- 简单
- 可解释
- 便于统计新增量
- 便于后续给不同操作套不同模板

这一层对应代码：

- [simple_diff.py](../modelers/simple_diff.py)

## 第三步：如何把新增接口变成 syzkaller fuzz 用例

这是 `/proc` fuzz 用例新增的核心思考。

这里的“新增用例”当前不是直接生成 program 级 `.syz` 文件，而是先生成 syzkaller 描述层：

- `proc_auto.txt`
- `proc_auto.txt.const`

为什么先做这一层：

- 这是 syzkaller 能编译和消费的正式输入
- 先把描述层打通，后续 program 级样例才能稳定生成
- 描述层失败时，问题更容易定位

### 当前的最小建模策略

对每个 `/proc` 节点，先生成一个 `openat$proc_*` 别名，然后按操作能力追加模板。

文件型节点：

- `read` -> `read$proc_*`
- `write` -> `write$proc_*`
- `lseek` -> `lseek$proc_*`
- `ioctl` -> `ioctl$proc_*`
- `mmap` -> `mmap$proc_*`
- `poll` -> `poll$proc_*` 和对应 `pollfd$proc_*`

目录型节点：

- `open` -> `openat$proc_*`
- `getdents64` 复用通用 syscall，不单独重写 syscall 原型

### 为什么 `ioctl/mmap/poll` 也是模板化处理

这几个操作很容易走向过度建模，但在当前阶段更稳的做法是：

- 先生成可编译、可消费的最小别名
- 不急于在这一层建模复杂命令字、复杂结构体和约束

例如：

- `ioctl$proc_*` 先用 `cmd int32, arg buffer[in]`
- `mmap$proc_*` 直接复用通用 `mmap` 参数形式
- `poll$proc_*` 通过 `pollfd$proc_*` 把 fd 类型约束到对应资源

这样做的价值在于：

- 能先把 `/proc` 相关的 syscall 描述接入 syzkaller
- 后续只需要在具体操作上逐步增强，而不用推翻整个生成链路

这一层对应代码：

- [minimal.py](../generators/syzkaller/minimal.py)

## 第四步：为什么必须有编译验证

如果第 3 步生成完就结束，很容易出现一种假成功：

- 文件看起来生成了
- 但 syzkaller 实际不能解析或不能编译

所以必须把第 4 步单独保留出来，运行：

- `make descriptions`

并把编译输出转成结构化诊断。

这一层单独存在的价值：

- 第 3 步可以专注生成
- 第 4 步可以专注报错归因
- 后续如果引入自动修复，也应该优先放在第 4 步之后

这一层对应代码：

- [syzkaller_build.py](../validators/syzkaller_build.py)

## 为什么保留分步骤脚本

虽然已经有统一入口：

- [proc_workflow.py](../workflows/proc_workflow.py)

但对 `/proc` fuzz 用例新增这类任务来说，逐步观察每一步输出仍然很重要。

因此保留以下操作面：

- discover 验证脚本
- diff demo / 抽样验证脚本
- generate demo / 验证脚本
- validate demo 脚本

这样可以分别回答不同问题：

- 第 1 步到底发现了什么
- 第 2 步为什么认定它是新增接口
- 第 3 步到底生成了哪些 syzkaller 描述
- 第 4 步为什么编译通过或失败

## 当前结论

当前 `/proc` 流程已经形成一条稳定的新增用例链路：

1. 从 Linux 源码发现 `/proc` 节点和操作能力
2. 将结果展开成接口项并与 baseline 做差
3. 生成 syzkaller 描述文件
4. 用编译验证生成结果是否有效

并且当前已经同时具备两套可执行输出：

- 现有运行格式
- v2 统一协议格式

也就是说，`discover_v2 -> diff_v2 -> generate_v2 -> validate_v2` 现在已经不是纸面设计，而是可以真实生成 syzkaller 描述并通过编译验证的执行链。

这条链路当前已经能稳定处理：

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

## 后续思考

下一阶段更值得投入的方向有两个：

- 让第 1 步识别更多真实的复杂 `/proc` 操作节点
- 让第 3 步从“最小模板生成”逐步走向“复杂参数建模”
