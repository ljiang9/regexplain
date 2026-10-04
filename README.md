# regexplain

正则表达式解释 + 本地测试工作台：一半是 LLM，一半是本地工具。

- `--explain`：让 LLM 用中文把任意正则**逐段拆解**成表格（片段 | 含义 | 示例匹配）
- `--test`：**纯本地**，用 Python `re` 逐个测试字符串，显示匹配结果和捕获组——不需要 API key，不联网
- `--gen`：用中文描述让 LLM **生成**正则，然后工具**立刻在本地用 `re` 验证**（闭环：生成 → 本地实测 → 逐条报告通过/未通过）

## 安装

零依赖，Python 3.10+ 自带标准库即可：

```bash
python3 -m regexplain --help
```

## 快速开始

```bash
# 1. 解释正则（需要 OPENAI_API_KEY）
export OPENAI_API_KEY="sk-..."
regexplain "(\d{4})-(\d{2})" --explain

# 2. 本地测试（不需要 key）
regexplain "^[\w.]+@\w+\.\w+$" --test "test@example.com" "not-an-email"

# 3. 生成 + 本地闭环验证（需要 key；测试本身在本地跑）
regexplain --gen "匹配中国手机号" --test "13812345678" "12345"

# 4. 只看编译是否合法
regexplain "([a-z]+"
```

## 三种模式

| 模式 | 是否需要 key | 是否联网 | 说明 |
|---|---|---|---|
| `--explain` | ✅ | ✅ | LLM 逐段解释，`--lang en` 可切英文 |
| `--test` | ❌ | ❌ | 纯本地 `re.search` 语义，显示捕获组 |
| `--gen` | ✅（生成时） | ✅（生成时） | 生成后本地验证不联网 |
| `--dry-run` | ❌ | ❌ | LLM 模式下只打印将要发送的 prompt |

环境变量：`OPENAI_API_KEY`（LLM 模式必需）、`OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`，兼容第三方）、`OPENAI_MODEL`（默认 `gpt-4o-mini`）。

## 诚实说明

- 解释质量取决于模型；表格是**模型生成**的，不是解析器算出来的，复杂正则请交叉核对。
- 本地测试用的是 **Python `re` 语义**（`re.search`），和其他语言（JS、Go、Rust）的正则引擎有细微差别，跨语言使用前请在目标环境复测。

## License

MIT — 详见 [LICENSE](LICENSE)。
