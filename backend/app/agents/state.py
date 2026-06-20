"""
KMatch 多智能体全局状态定义

对齐 data/prompts/01_orchestrator_agent.txt 中的全局状态结构。
所有 Agent 节点共享此 State，主控调度 Agent 负责流转与更新。

字段语义:
  - user_profile:   用户能力画像 v3（学情检测前为空 dict，检测后填充）
                    对齐 data/user_profiles/profile_schema.json
  - assessment:     测评中间数据（题目/答案/逐题得分），学情检测节点产出
  - review_results: 内容审核报告，对齐 05_content_reviewer_agent.txt 输出格式
  - retry_count:    当前"生成→审核→打回"循环已执行轮数
  - max_retries:    最大重试轮数（orchestrator prompt 规则3 默认 3）
  - orchestration_log: 追加式执行日志，Annotated 合并避免节点间覆盖
"""

from typing import Annotated, Literal, TypedDict


# 场景类型
Scene = Literal["no_project", "with_project"]


def _append_log(left: list, right: list) -> list:
    """orchestration_log 的 reducer：右值追加到左值末尾。

    LangGraph 对 Annotated 字段会调用此 reducer 合并节点返回的新日志与已有日志，
    避免每个节点返回完整日志列表导致覆盖。沿用 week1_demos/langgraph_demo 的模式。
    """
    return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    """多 Agent 共享全局状态。

    total=False: 所有字段可选，便于初始状态只填部分字段、各节点按需补充。
    """

    # --- 会话元信息 ---
    session_id: str
    scene: Scene

    # --- 用户输入 ---
    target_direction: str          # 学习目标方向（自然语言）
    mode: Literal["demo", "interactive"]  # demo=LLM自动作答跑通闭环; interactive=待前端提交答案
    known_topics: list             # 用户自报已学节点 [{node_id, mastery}]

    # --- 学情检测产出 ---
    user_profile: dict             # 画像 v3，对齐 profile_schema.json
    assessment: dict               # {questions, answers, per_node, correct_count, total_count}

    # --- 内容审核产出 ---
    review_results: dict           # {passed, overall_score, dimensions, verdict, retry_hint, reviewed_at}

    # --- 知识图谱管控产出 (第3周) ---
    knowledge_graph: dict          # {learning_path, path_node_ids, estimated_total_hours, node_status_updates, assembled_at}

    # --- 领域知识生成产出 (第4周) ---
    generated_content: dict        # {resources[], node_count, content_types, generated_at}; resources 元素含 content_type/target_node_id/source_nodes/content

    # --- 阶段标志 (BUG-031: 防内容阶段空资源回退画像模式致无限循环) ---
    # content_generator 首次运行后置 True；reviewer 据此判断审核对象，
    # 即使本轮 resources 为空 (路径空/生成全失败) 也保持内容模式 (判不通过)，
    # 避免 reviewer 回退画像模式 + 画像通过 → graph_controller 无限循环。
    content_phase_entered: bool

    # --- 有项目场景 (W6 batch2 接入 with_project workflow) ---
    # 本批 API 解析不经 workflow，这两个字段为契约预留：
    # project_graph 供 reviewer 图谱校验 / code_tester 反向标注风险节点消费，
    # 避免下游 Agent 重新解析代码。
    project_id: str
    project_graph: dict        # ParsedProject 序列化 {project_id, entities[], relations[], stats}

    # --- 循环控制 ---
    retry_count: int
    max_retries: int

    # --- 执行日志 ---
    orchestration_log: Annotated[list, _append_log]


def make_initial_state(
    target_direction: str,
    mode: str = "demo",
    known_topics: list = None,
    scene: str = "no_project",
    max_retries: int = 3,
) -> AgentState:
    """构造初始状态。学情检测节点将填充 user_profile / assessment。"""
    import uuid

    return AgentState(
        session_id=str(uuid.uuid4()),
        scene=scene,
        target_direction=target_direction,
        mode=mode,
        known_topics=known_topics or [],
        user_profile={},
        assessment={},
        review_results={"passed": False},
        retry_count=0,
        max_retries=max_retries,
        orchestration_log=[],
    )
