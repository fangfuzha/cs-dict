# cs-dict

计算机领域词汇字典收集
皆为 `dict` 格式以支持 linux `fcitx5` 框架

## 📚 词典列表（dict 目录下）

- `cainiao-coding.dict`: 菜鸟教程上关于编程的术语整理
- `google-ml.dict`: google 的机器学习术语表
- `jike-cs.dict`: 极客学院关键词
- `jiqizhixin-ml.dict`: 机器之心整理的人工智能词库
- `sougou-it.dict`: 搜狗输入法与计算机领域有关的热门词库
- `qinghua_it.dict`: 取掉词频的清华开放的 IT 词库
- `THUOCL_it.dict`: 保留词频的清华开放的 IT 词库
- `juejin-cs.dict`: 掘金社区的标签
- `CustomPinyinDictionary_Fcitx.dict`：来自 [CustomPinyinDictionary](https://github.com/wuhgit/CustomPinyinDictionary) **（自动更新）**
- `zhwiki-20250823.dict`：来自[fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki)**（自动更新）**，其源数据来源于中文维基百科的词条，包含大量通用词汇和专业术语。

## 🔧 如何使用

1. **手动使用**:

   - 将 `dict/` 目录下的 `.dict` 文件复制到 fcitx5 的用户词典目录
   - 通常位于 `~/.local/share/fcitx5/pinyin/dictionaries/`（如果使用拼音输入法的话）
   - 重启 fcitx5 使配置生效
   - rime 用户`注意`：rime 不支持 .dict 格式，需要转换为 rime 的自定义词典格式 .dict.yaml。

## 🔗 友链

- [cs-dict](https://github.com/ylfeng250/cs-dict) - 计算机领域词汇字典收集
- [CustomPinyinDictionary](https://github.com/wuhgit/CustomPinyinDictionary) - 自建拼音输入法词库
- [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) - 中文维基百科词条词库
