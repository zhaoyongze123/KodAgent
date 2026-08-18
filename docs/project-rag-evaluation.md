# 项目资料 RAG 评测

项目资料 RAG 的灰度依据是人工标注的真实资料集，不是模型自评或演示数据。评测只保存案例编号、预期文件/片段标识、版本和脱敏检索结果；不要提交用户问题全文、文件正文、文件路径、下载 URL、令牌或向量。

## 标注输入

`cases.jsonl` 每行一个案例，至少准备 40 条自然语言问题，覆盖项目方案、交通专题、进度报告、制度要求、简称/同义表达和精确文件名查询。

```json
{"id":"case-001","tags":["exact_file_name"],"expectedEvidence":[{"sourceType":"PROJECT_FILES","fileId":"123","chunkId":"456","contentVersion":"sha256-or-version"}],"forbiddenFileIds":["789"],"forbiddenLibraryIds":["321"]}
```

- `expectedEvidence`：人工确认应命中的文件/片段。项目资料和 KodCloud 目录使用 `fileId`；本地上传使用 `sourceType=LOCAL_UPLOAD + libraryId`。`chunkId`、`contentVersion` 存在时也会参与匹配。
- `tags`：精确文件名查询标注为 `exact_file_name`，用于防止混合检索削弱文件名检索。
- `forbiddenFileIds`、`forbiddenLibraryIds`：以同一用户身份查询时绝不能出现的文件或本地上传知识源，用于目录失权和本地 ACL 的权限回归。

## 结果输入

对同一份资料、同一用户身份和同一批案例，分别用服务端环境配置运行 `keyword`、`semantic`、`hybrid` 三次。`OA_AGENT_PROJECT_RAG_RETRIEVAL_MODE` 仅能通过 Secrets Overlay/部署环境设置，API 和模型工具无权覆盖。

`results.jsonl` 每行包含一个模式的一次结果：

```json
{"id":"case-001","mode":"hybrid","elapsedMs":82,"hits":[{"citationId":"资料 1","sourceType":"PROJECT_FILES","fileId":"123","libraryId":null,"chunkId":"456","name":"脱敏文件名.docx","contentVersion":"sha256-or-version","section":"第 2 章"}]}
```

检索服务返回异常时记录 `failureCode`，不要把异常当作空命中。

## 执行与门禁

```bash
python3 agent-python/src/project_rag_evaluation.py \
  --cases /secure/evals/cases.jsonl \
  --results /secure/evals/results.jsonl \
  --output /secure/evals/report.json \
  --require-gate
```

评测输出每种模式的 `Recall@5`、引用准确率、权限泄露数、平均耗时和覆盖率。只有同时满足以下条件，才可以设置 `OA_AGENT_PROJECT_RAG_ENABLED=true`：

1. 至少 40 条真实、人工标注案例，三种模式覆盖率均为 100%。
2. 混合检索 `Recall@5` 严格高于全文检索。
3. 精确文件名案例的混合召回不低于全文检索。
4. 任一模式均无权限泄露和运行时错误。

## 统一知识源补充样例

在 40 条案例中至少加入以下四类：KodCloud 目录文件失权、目录文件版本变更、本地上传资料的指定部门命中、同一资料对未授权用户的 `forbiddenLibraryIds` 拒绝命中。目录源与本地上传均应分别跑三种检索模式；embedding 不可用时记录 `keyword_fallback`，不能将服务失败记作零命中。

评测失败时保持全文检索，排查资料抽取、版本同步、权限过滤或 embedding 服务，而不是放宽权限、忽略失败或修改标注来通过门禁。
