/**
 * 学情画像 / 知识图谱类型契约 (C1.5/C3, 从 chat.js buildSystemPrompt 抽出)。
 *
 * 此前 chat.js 的 buildSystemPrompt 硬编码 assessment store 的内部字段名
 * (profile.theory_level / weak_topics[].name/.node_id / knowledgeGraph.learning_path.length /
 * estimated_total_hours)。assessment 改 schema 时 chat 提示词会静默崩, 无契约。
 *
 * 这里用 JSDoc 声明类型 + 类型化访问 helper, 字段名集中一处; buildSystemPrompt 经 helper 读取。
 * 不改运行时行为, 只加契约。术语对齐 CONTEXT.md "学情画像 (profile v3)"。
 */

/**
 * @typedef {Object} ProfileTopic
 * @property {string} [name]      知识点名称
 * @property {string} [node_id]   知识图谱节点 ID
 */

/**
 * @typedef {Object} Profile  学情画像 (对齐 backend profile_schema.json)
 * @property {number} [theory_level]    理论掌握等级 (0-5)
 * @property {number} [practice_level]  实践掌握等级 (0-5)
 * @property {ProfileTopic[]} [weak_topics]  薄弱知识点
 * @property {{node_id: string}[]} [known_topics]  已掌握知识点
 */

/**
 * @typedef {Object} LearningPathGraph  学习路径图谱 (assessment.knowledgeGraph)
 * @property {unknown[]} [learning_path]        学习路径节点
 * @property {number} [estimated_total_hours]   预计总学时
 */

/** profile 是否存在且有效。 */
export function hasProfile(profile) {
  return !!profile && typeof profile === 'object'
}

/** 理论水平 (0-5), 缺失返回 null。 */
export function profileTheoryLevel(profile) {
  return hasProfile(profile) && profile.theory_level != null ? profile.theory_level : null
}

/** 实操水平 (0-5), 缺失返回 null。 */
export function profilePracticeLevel(profile) {
  return hasProfile(profile) && profile.practice_level != null ? profile.practice_level : null
}

/** 薄弱知识点名称列表 (取 name, 缺则 node_id, 最多 limit 个)。 */
export function profileWeakTopicNames(profile, limit = 5) {
  if (!hasProfile(profile)) return []
  const weak = Array.isArray(profile.weak_topics) ? profile.weak_topics : []
  return weak.slice(0, limit).map((t) => t?.name || t?.node_id || '').filter(Boolean)
}

/** 学习路径节点数, 缺失返回 0。 */
export function learningPathLength(kg) {
  return kg?.learning_path?.length || 0
}

/** 预计总学时 (保留 1 位小数), 缺失返回 null。 */
export function learningEstimatedHours(kg) {
  const h = kg?.estimated_total_hours
  return typeof h === 'number' ? (h.toFixed ? Number(h.toFixed(1)) : h) : null
}
