# `/proc` 子系统参考总结

本文件用于作为新增模块时的对照样例，说明当前 `/proc` 是如何接入 `hm-ai-fuzz` 四步流程的。

## 1. 模块特点

- 子系统：`proc`
- 当前默认路径提示：`fs/proc`
- 目标对象：`/proc` 下的文件、目录、符号链接或动态节点
- 当前发现方式：从 Linux 源码中的注册点和路径解析逻辑推导接口对象，再结合 ops 结构确认支持能力

## 2. Discover

### 输入

- `kernel_src`
- `target_subsystem=proc`
- `scope_path=fs/proc`
- `search_method`
- `scan_mode`
- `semantic_signals`

### 输出

- `discover.json`
- `discover-llm.json`
- `discover-merged.json`

### 当前 discover 重点

- 找到 `/proc` 节点注册点
- 解析节点路径
- 解析 `proc_ops`、`file_operations` 等结构
- 提取能力集合
- 记录源码位置和模块信息

### 当前 discover 输出项典型字段

- `subsystem=proc`
- `target=/proc/...`
- `kind=virtual_file` 或其他节点类型
- `capabilities`
- `source.file`
- `source.line`
- `source.symbol`
- `metadata.node_type`
- `metadata.registration_kind`

## 3. Diff

### 输入

- `discover-merged.json`
- baseline JSON

### 输出

- `diff.json`
- `diff-v2.json`

### 当前 diff 粒度

当前 `/proc` 差集不是只按节点路径，而是进一步展开到：

- `subsystem:target:op`

也就是同一个 `/proc` 节点会被拆成多个操作级新增项。

## 4. Generate

### 输入

- `diff.json`
- `syzkaller_dir`

### 输出

- `generate.json`
- `generate-v2.json`
- `../syzkaller/sys/linux/proc_auto.txt`
- `../syzkaller/sys/linux/proc_auto.txt.const`
- 可选的中间 case 产物，例如 `out/cases/proc/*.json`

### 当前生成策略

当前生成器是最小策略：

- 为每个目标节点生成 `openat` 别名
- 对已确认支持的通用操作生成最小 syzkaller 映射
- 对不支持或当前未实现的复杂能力保持保守
- 如有中间 case JSON，只作为辅助跟踪和后续 richer model 的输入，不替代最终 `syzkaller` 描述文件

### 当前优先支持的操作

- `open`
- `read`
- `write`
- `lseek`
- `getdents64`
- `ioctl`
- `mmap`
- `poll`

## 5. Validate

### 输入

- 第三步生成结果
- `syzkaller_dir`
- `make_target=descriptions`

### 输出

- `validate.json`
- `validate-v2.json`
- `publish.json`

### 当前验证方式

- 将生成的描述写入外部 `syzkaller` 仓库
- 运行 `make descriptions`
- 收集构建结果和失败诊断
- 只有成功进入 `../syzkaller/sys/linux/proc_auto.txt` 并通过验证，才算该 proc 用例真正接入完成

## 6. 对新增模块的启发

如果其他模块要新增用例，优先先回答这些问题：

- 这个模块有没有像 `/proc` 一样稳定的注册点
- 能否解析出稳定的目标对象
- 能否从 ops 结构可靠提取操作集合
- 差集粒度是否仍然适合 `target + op`
- 现有最小 generator 是否足够
- 如果不够，最小扩展点是什么
- 最终应该写入 `syzkaller` 仓库中的哪个描述文件
