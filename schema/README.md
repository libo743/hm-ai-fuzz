# JSON Schema Draft

这个目录放 `hm-ai-fuzz` 面向全模块统一接口协议的 JSON Schema 草案。

目标：

- 用统一协议描述 discover / diff / generate / validate 四步产物
- 同时覆盖 `/proc`、`sysfs`、文件系统、网络、设备节点和直接 syscall
- 把“接口对象层”和“syscall 绑定层”明确拆开

当前 `/proc` 流程的 discover 阶段已经进一步拆成：

- base discover
- llm discover
- merged discover

因此统一协议后续也需要能容纳：

- `discover_v2`
- `discover_llm_v2`
- `discover_merged_v2`

同时 discover 的 `scope` 已经从“路径主导”调整成“语义目标主导”，当前建议至少表达：

- `target_subsystem`
- `scope_path`
- `scope_strategy`
- `semantic_signals`

文件说明：

- [common.schema.json](/home/libo/work/hm-ai-fuzz/schema/common.schema.json)
  通用定义，供其他 schema 复用
- [discover.schema.json](/home/libo/work/hm-ai-fuzz/schema/discover.schema.json)
  第 1 步 discover 输出
- [diff.schema.json](/home/libo/work/hm-ai-fuzz/schema/diff.schema.json)
  第 2 步 diff 输出
- [generate.schema.json](/home/libo/work/hm-ai-fuzz/schema/generate.schema.json)
  第 3 步 generate 输出
- [validate.schema.json](/home/libo/work/hm-ai-fuzz/schema/validate.schema.json)
  第 4 步 validate 输出
- [pipeline.schema.json](/home/libo/work/hm-ai-fuzz/schema/pipeline.schema.json)
  完整四步总输出

说明：

- 这套 schema 的重点是为后续各模块负责人定义统一交付物
- 当前 `/proc` 实现已经能同时导出并执行 `discover_v2 / discover_llm_v2 / discover_merged_v2 / diff_v2 / generate_v2 / validate_v2`
- 当前 schema 仍然是面向全模块扩展的协议草案，后续接入新模块时允许继续细化字段和约束
