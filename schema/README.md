# JSON Schema Draft

这个目录放 `hm-ai-fuzz` 面向全模块统一接口协议的 JSON Schema 草案。

目标：

- 用统一协议描述 discover / diff / generate / validate 四步产物
- 同时覆盖 `/proc`、`sysfs`、文件系统、网络、设备节点和直接 syscall
- 把“接口对象层”和“syscall 绑定层”明确拆开

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

- 这是协议草案，不要求当前 `/proc` 实现立刻完全满足
- 这套 schema 的重点是为后续各模块负责人定义统一交付物
- 当前实现如果要接入这套 schema，建议先从 discover 和 diff 两步开始收敛
