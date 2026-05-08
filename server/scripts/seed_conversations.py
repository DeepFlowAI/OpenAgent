"""
Test data generator for conversation & conversation steps.
Uses actual API endpoints to create realistic conversation data.

Usage: python seed_conversations.py
"""

import requests
import time
import random

BASE_URL = "http://127.0.0.1:5001/api/v1"
TENANT_ID = "T2026032303M"
AGENT_ID = 8

TOOLS = {
    "knowledge_search": {"id": 8, "type": "search", "name": "knowledge_search"},
    "notebook": {"id": 4, "type": "notebook", "name": "notebook"},
    "tool_response_fetch": {"id": 5, "type": "tool_response_fetch", "name": "tool_response_fetch"},
    "doc_query": {"id": 9, "type": "doc_query", "name": "doc_query"},
    "python_code": {"id": 3, "type": "python_code", "name": "python_code"},
}

def api(method, path, json=None, params=None):
    url = f"{BASE_URL}/{path}"
    resp = getattr(requests, method)(url, json=json, params=params)
    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


def create_conversation(user_id, source="chat", title=None):
    data = {
        "tenant_id": TENANT_ID,
        "agent_id": AGENT_ID,
        "user_id": user_id,
        "source": source,
        "title": title,
    }
    return api("post", f"agents/{AGENT_ID}/conversations", json=data)


def create_step(conv_id, step_data):
    return api(
        "post",
        f"agents/{AGENT_ID}/conversations/{conv_id}/steps",
        json=step_data,
        params={"tenant_id": TENANT_ID},
    )


def end_conversation(conv_id):
    return api("post", f"agents/{AGENT_ID}/conversations/{conv_id}/end")


# ─────────────────────────────────────────────
# Conversation 1: Multi-round with search + notebook (ended)
# ─────────────────────────────────────────────
def seed_conv1():
    print("Creating conversation 1: multi-round search + notebook...")
    conv = create_conversation("user_001", "chat")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    # Round 1: user asks about return policy
    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "帮我查一下我们的退换货政策，特别是关于电子产品的部分",
        "status": "success",
    })

    # LLM call 1: thinks, decides to search
    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户想了解退换货政策中关于电子产品的具体规定。我需要先搜索知识库中的退换货政策文档，找到与电子产品相关的内容。让我使用 knowledge_search 工具来检索。",
        "request_messages": [
            {"role": "system", "content": "你是一个专业的客服助手，请根据知识库内容回答用户问题。"},
            {"role": "user", "content": "帮我查一下我们的退换货政策，特别是关于电子产品的部分"},
        ],
        "request_tools": [
            {"type": "function", "function": {"name": "knowledge_search", "description": "Search knowledge base"}},
            {"type": "function", "function": {"name": "notebook", "description": "Manage notebook"}},
        ],
        "request_params": {"temperature": 0.01, "max_tokens": 4096},
        "response_tool_calls": [
            {
                "id": "call_001",
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "arguments": '{"query": "电子产品退换货政策", "brief": "检索电子产品退换货政策相关内容"}',
                },
            }
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 1520,
        "output_tokens": 380,
        "total_tokens": 1900,
        "duration_ms": 2340,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    # Tool call 1: knowledge_search
    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "knowledge_search",
        "tool_type": "search",
        "tool_call_id": "call_001",
        "tool_arguments": {"query": "电子产品退换货政策", "brief": "检索电子产品退换货政策相关内容"},
        "tool_response": '<search_results tool_response_id="sr_8f2a">\n<result rank="1" doc_id="doc_102" slice_id="s_2041">\n## 电子产品退换货规定\n1. 自签收之日起7天内，产品存在质量问题可无理由退货\n2. 15天内可换货\n3. 拆封后非质量问题不支持退货\n4. 需保留原包装及配件\n</result>\n<result rank="2" doc_id="doc_102" slice_id="s_2042">\n## 特殊电子产品说明\n- 手机、平板：激活后仅支持换货不支持退货\n- 耳机类：拆封后不支持退换\n- 电脑类：开机激活后15天内仅支持换货\n</result>\n</search_results>',
        "brief": "检索电子产品退换货政策相关内容",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    # LLM call 2: thinks, decides to save to notebook
    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "搜索结果返回了两个相关切片，包含了电子产品退换货的具体规定。信息很全面，我先把关键信息记到笔记里，然后整理回复给用户。",
        "request_messages": [
            {"role": "system", "content": "你是一个专业的客服助手..."},
            {"role": "user", "content": "帮我查一下我们的退换货政策，特别是关于电子产品的部分"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_001", "type": "function", "function": {"name": "knowledge_search", "arguments": '{"query":"电子产品退换货政策","brief":"检索电子产品退换货政策相关内容"}'}}]},
            {"role": "tool", "tool_call_id": "call_001", "content": "(search results...)"},
        ],
        "request_tools": [
            {"type": "function", "function": {"name": "knowledge_search"}},
            {"type": "function", "function": {"name": "notebook"}},
        ],
        "request_params": {"temperature": 0.01, "max_tokens": 4096},
        "response_tool_calls": [
            {
                "id": "call_002",
                "type": "function",
                "function": {
                    "name": "notebook",
                    "arguments": '{"action": "add", "brief": "记录电子产品退换货关键规则", "items": [{"text": "电子产品7天退货15天换货", "doc_id": "doc_102", "slice_id": "s_2041"}]}',
                },
            }
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 2800,
        "output_tokens": 420,
        "total_tokens": 3220,
        "duration_ms": 3100,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    # Tool call 2: notebook
    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "notebook",
        "tool_type": "notebook",
        "tool_call_id": "call_002",
        "tool_arguments": {"action": "add", "brief": "记录电子产品退换货关键规则", "items": [{"text": "电子产品7天退货15天换货", "doc_id": "doc_102", "slice_id": "s_2041"}]},
        "tool_response": '<notebook_response>\n<status>success</status>\n<notebook_size>1</notebook_size>\n</notebook_response>',
        "brief": "记录电子产品退换货关键规则",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    # LLM call 3: final reply
    llm3 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "笔记已保存。现在我来整理搜索到的信息，给用户一个清晰的回复。",
        "content": "根据我们的退换货政策，电子产品的具体规定如下：\n\n**通用规则：**\n1. 自签收之日起 **7 天内**，产品存在质量问题可无理由退货\n2. **15 天内**可换货\n3. 拆封后非质量问题不支持退货\n4. 需保留原包装及配件\n\n**特殊品类说明：**\n- **手机、平板**：激活后仅支持换货，不支持退货\n- **耳机类**：拆封后不支持退换\n- **电脑类**：开机激活后 15 天内仅支持换货\n\n如有具体情况需要咨询，请告诉我更多细节，我可以帮你进一步确认。",
        "request_messages": [
            {"role": "system", "content": "你是一个专业的客服助手..."},
            {"role": "user", "content": "帮我查一下我们的退换货政策..."},
        ],
        "finish_reason": "stop",
        "input_tokens": 3600,
        "output_tokens": 520,
        "total_tokens": 4120,
        "duration_ms": 4500,
        "status": "success",
    })
    llm3_id = llm3["id"] if llm3 else None

    # Assistant message
    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "根据我们的退换货政策，电子产品的具体规定如下：\n\n**通用规则：**\n1. 自签收之日起 **7 天内**，产品存在质量问题可无理由退货\n2. **15 天内**可换货\n3. 拆封后非质量问题不支持退货\n4. 需保留原包装及配件\n\n**特殊品类说明：**\n- **手机、平板**：激活后仅支持换货，不支持退货\n- **耳机类**：拆封后不支持退换\n- **电脑类**：开机激活后 15 天内仅支持换货\n\n如有具体情况需要咨询，请告诉我更多细节，我可以帮你进一步确认。",
        "parent_step_id": llm3_id,
        "status": "success",
    })

    # Round 2: follow-up question
    create_step(cid, {
        "round_number": 2,
        "step_type": "user_message",
        "content": "我买了一台笔记本电脑，已经开机激活了，但是发现屏幕有坏点，这种情况可以退货吗？",
        "status": "success",
    })

    llm4 = create_step(cid, {
        "round_number": 2,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户的笔记本电脑已经激活，但屏幕有坏点。根据之前搜索到的规则：\n1. 电脑类开机激活后15天内仅支持换货\n2. 但屏幕坏点属于质量问题\n\n我需要再搜索一下关于质量问题的特殊处理规定，看看坏点是否有单独的标准。",
        "request_messages": [{"role": "user", "content": "我买了一台笔记本..."}],
        "response_tool_calls": [
            {
                "id": "call_003",
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "arguments": '{"query": "笔记本电脑屏幕坏点质量问题退换标准", "brief": "查询屏幕坏点相关的退换货质量标准"}',
                },
            }
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 4200,
        "output_tokens": 350,
        "total_tokens": 4550,
        "duration_ms": 2800,
        "status": "success",
    })
    llm4_id = llm4["id"] if llm4 else None

    create_step(cid, {
        "round_number": 2,
        "step_type": "tool_call",
        "tool_name": "knowledge_search",
        "tool_type": "search",
        "tool_call_id": "call_003",
        "tool_arguments": {"query": "笔记本电脑屏幕坏点质量问题退换标准", "brief": "查询屏幕坏点相关的退换货质量标准"},
        "tool_response": '<search_results tool_response_id="sr_9b3c">\n<result rank="1" doc_id="doc_102" slice_id="s_2045">\n## 屏幕质量判定标准\n- 亮点/坏点 ≥ 3个：判定为质量问题，支持退货\n- 亮点/坏点 < 3个：属于行业正常范围，仅支持换货\n- 检测需在签收15天内到官方售后进行\n</result>\n</search_results>',
        "brief": "查询屏幕坏点相关的退换货质量标准",
        "parent_step_id": llm4_id,
        "status": "success",
    })

    llm5 = create_step(cid, {
        "round_number": 2,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "找到了具体标准。屏幕坏点≥3个算质量问题可以退货，<3个只能换货。我需要询问用户坏点数量来给出具体建议。",
        "content": "关于笔记本电脑屏幕坏点的情况，我查到了具体的判定标准：\n\n**屏幕质量判定：**\n- 坏点/亮点 **≥ 3 个**：判定为质量问题，**支持退货**\n- 坏点/亮点 **< 3 个**：属于行业正常范围，**仅支持换货**\n\n**注意事项：**\n- 需在签收 **15 天内**到官方售后进行检测\n- 电脑类已激活，换货渠道是可以的\n\n请问你的屏幕上有几个坏点？如果有 3 个或以上，可以直接申请退货；如果不到 3 个，建议走换货流程。",
        "finish_reason": "stop",
        "input_tokens": 5100,
        "output_tokens": 480,
        "total_tokens": 5580,
        "duration_ms": 5200,
        "status": "success",
    })
    llm5_id = llm5["id"] if llm5 else None

    create_step(cid, {
        "round_number": 2,
        "step_type": "assistant_message",
        "content": "关于笔记本电脑屏幕坏点的情况，我查到了具体的判定标准：\n\n**屏幕质量判定：**\n- 坏点/亮点 **≥ 3 个**：判定为质量问题，**支持退货**\n- 坏点/亮点 **< 3 个**：属于行业正常范围，**仅支持换货**\n\n**注意事项：**\n- 需在签收 **15 天内**到官方售后进行检测\n- 电脑类已激活，换货渠道是可以的\n\n请问你的屏幕上有几个坏点？如果有 3 个或以上，可以直接申请退货；如果不到 3 个，建议走换货流程。",
        "parent_step_id": llm5_id,
        "status": "success",
    })

    end_conversation(cid)
    print(f"  ✓ Conversation 1 done (2 rounds, ended)")


# ─────────────────────────────────────────────
# Conversation 2: API source, single round with doc_query (ended)
# ─────────────────────────────────────────────
def seed_conv2():
    print("Creating conversation 2: API source, doc_query...")
    conv = create_conversation("api_client_prod", "api")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "列出所有关于退换货的文档",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户想查看所有退换货相关文档的列表，我应该使用 doc_query 工具按关键词搜索文档标题。",
        "response_tool_calls": [
            {
                "id": "call_010",
                "type": "function",
                "function": {
                    "name": "doc_query",
                    "arguments": '{"query": "退换货", "brief": "查询退换货相关文档列表"}',
                },
            }
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 980,
        "output_tokens": 210,
        "total_tokens": 1190,
        "duration_ms": 1800,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "doc_query",
        "tool_type": "doc_query",
        "tool_call_id": "call_010",
        "tool_arguments": {"query": "退换货", "brief": "查询退换货相关文档列表"},
        "tool_response": '<doc_query_results>\n<doc id="doc_102" title="退换货政策 v2.3" updated="2026-03-15" slices="28"/>\n<doc id="doc_115" title="售后服务手册" updated="2026-03-10" slices="45"/>\n<doc id="doc_120" title="消费者权益保障方案" updated="2026-02-28" slices="32"/>\n</doc_query_results>',
        "brief": "查询退换货相关文档列表",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": False,
        "content": "找到以下与退换货相关的文档：\n\n| 文档 ID | 标题 | 更新日期 | 切片数 |\n|---------|------|----------|--------|\n| doc_102 | 退换货政策 v2.3 | 2026-03-15 | 28 |\n| doc_115 | 售后服务手册 | 2026-03-10 | 45 |\n| doc_120 | 消费者权益保障方案 | 2026-02-28 | 32 |\n\n共 3 篇文档。如需查看某篇文档的详细内容，请告诉我文档 ID。",
        "finish_reason": "stop",
        "input_tokens": 1600,
        "output_tokens": 320,
        "total_tokens": 1920,
        "duration_ms": 2100,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "找到以下与退换货相关的文档：\n\n| 文档 ID | 标题 | 更新日期 | 切片数 |\n|---------|------|----------|--------|\n| doc_102 | 退换货政策 v2.3 | 2026-03-15 | 28 |\n| doc_115 | 售后服务手册 | 2026-03-10 | 45 |\n| doc_120 | 消费者权益保障方案 | 2026-02-28 | 32 |\n\n共 3 篇文档。如需查看某篇文档的详细内容，请告诉我文档 ID。",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    end_conversation(cid)
    print(f"  ✓ Conversation 2 done (1 round, API source, ended)")


# ─────────────────────────────────────────────
# Conversation 3: Active conversation (still ongoing)
# ─────────────────────────────────────────────
def seed_conv3():
    print("Creating conversation 3: active, single round so far...")
    conv = create_conversation("user_zhang_wei", "chat")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "请帮我分析一下上个月的销售数据趋势",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户需要分析上个月的销售数据趋势。我应该先搜索知识库中的销售数据报告，然后用 python_code 工具进行数据分析和可视化。让我先搜索相关数据。",
        "response_tool_calls": [
            {
                "id": "call_020",
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "arguments": '{"query": "2026年2月销售数据月度报告", "brief": "搜索上月销售数据报告"}',
                },
            }
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 1200,
        "output_tokens": 280,
        "total_tokens": 1480,
        "duration_ms": 2000,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "knowledge_search",
        "tool_type": "search",
        "tool_call_id": "call_020",
        "tool_arguments": {"query": "2026年2月销售数据月度报告", "brief": "搜索上月销售数据报告"},
        "tool_response": '<search_results tool_response_id="sr_c4d1">\n<result rank="1" doc_id="doc_201" slice_id="s_5001">\n## 2026年2月销售概览\n总销售额：¥2,450,000\n同比增长：12.5%\n环比下降：3.2%\n订单数：3,280\n客单价：¥747\n</result>\n</search_results>',
        "brief": "搜索上月销售数据报告",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "找到了基本的销售数据。现在我需要获取更详细的数据来做趋势分析。让我再搜索一下每周的明细数据，然后用 Python 来分析趋势。",
        "content": "根据搜索到的数据，2026年2月的销售概况如下：\n\n- **总销售额**：¥2,450,000\n- **同比增长**：12.5%\n- **环比下降**：3.2%（受春节假期影响）\n- **总订单数**：3,280 单\n- **客单价**：¥747\n\n整体趋势来看，同比保持了两位数增长，但环比有小幅下降，主要受春节假期影响。如果需要更详细的按周趋势分析或品类拆分，请告诉我。",
        "finish_reason": "stop",
        "input_tokens": 2400,
        "output_tokens": 380,
        "total_tokens": 2780,
        "duration_ms": 3400,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "根据搜索到的数据，2026年2月的销售概况如下：\n\n- **总销售额**：¥2,450,000\n- **同比增长**：12.5%\n- **环比下降**：3.2%（受春节假期影响）\n- **总订单数**：3,280 单\n- **客单价**：¥747\n\n整体趋势来看，同比保持了两位数增长，但环比有小幅下降，主要受春节假期影响。如果需要更详细的按周趋势分析或品类拆分，请告诉我。",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    # Not ending this one — keep it active
    print(f"  ✓ Conversation 3 done (1 round, still ACTIVE)")


# ─────────────────────────────────────────────
# Conversation 4: Multi-tool with tool_response_fetch (ended)
# ─────────────────────────────────────────────
def seed_conv4():
    print("Creating conversation 4: tool_response_fetch usage...")
    conv = create_conversation("user_li_na", "chat")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "帮我找一下关于新员工入职培训的资料",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户需要新员工入职培训资料，让我搜索知识库。",
        "response_tool_calls": [
            {"id": "call_030", "type": "function", "function": {"name": "knowledge_search", "arguments": '{"query": "新员工入职培训", "brief": "搜索新员工入职培训资料"}'}},
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 900,
        "output_tokens": 180,
        "total_tokens": 1080,
        "duration_ms": 1500,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "knowledge_search",
        "tool_type": "search",
        "tool_call_id": "call_030",
        "tool_arguments": {"query": "新员工入职培训", "brief": "搜索新员工入职培训资料"},
        "tool_response": '<search_results tool_response_id="sr_d5e2">\n<result rank="1" doc_id="doc_301" slice_id="s_7001">\n## 新员工入职流程\n第一周：公司文化与规章制度培训...(truncated)\n</result>\n</search_results>',
        "brief": "搜索新员工入职培训资料",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    # LLM decides to fetch the full response
    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "搜索结果被截断了，我需要用 tool_response_fetch 获取完整的搜索结果。",
        "response_tool_calls": [
            {"id": "call_031", "type": "function", "function": {"name": "tool_response_fetch", "arguments": '{"tool_response_id": "sr_d5e2", "brief": "获取入职培训搜索结果完整内容"}'}},
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 1800,
        "output_tokens": 150,
        "total_tokens": 1950,
        "duration_ms": 1200,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "tool_response_fetch",
        "tool_type": "tool_response_fetch",
        "tool_call_id": "call_031",
        "tool_arguments": {"tool_response_id": "sr_d5e2", "brief": "获取入职培训搜索结果完整内容"},
        "tool_response": '<full_response>\n## 新员工入职流程\n第一周：公司文化与规章制度培训\n第二周：部门业务介绍与导师对接\n第三周：岗位技能培训\n第四周：考核与转正评估\n\n### 必备材料\n- 身份证复印件\n- 学历证明\n- 体检报告\n- 离职证明\n- 银行卡信息\n</full_response>',
        "brief": "获取入职培训搜索结果完整内容",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    llm3 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "现在我有了完整的入职培训信息，可以给用户一个全面的回复了。",
        "content": "以下是新员工入职培训的详细安排：\n\n**培训周期（4周）：**\n- **第一周**：公司文化与规章制度培训\n- **第二周**：部门业务介绍与导师对接\n- **第三周**：岗位技能培训\n- **第四周**：考核与转正评估\n\n**入职必备材料：**\n- 身份证复印件\n- 学历证明\n- 体检报告\n- 离职证明\n- 银行卡信息\n\n还有其他需要了解的吗？",
        "finish_reason": "stop",
        "input_tokens": 2600,
        "output_tokens": 350,
        "total_tokens": 2950,
        "duration_ms": 2800,
        "status": "success",
    })
    llm3_id = llm3["id"] if llm3 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "以下是新员工入职培训的详细安排：\n\n**培训周期（4周）：**\n- **第一周**：公司文化与规章制度培训\n- **第二周**：部门业务介绍与导师对接\n- **第三周**：岗位技能培训\n- **第四周**：考核与转正评估\n\n**入职必备材料：**\n- 身份证复印件\n- 学历证明\n- 体检报告\n- 离职证明\n- 银行卡信息\n\n还有其他需要了解的吗？",
        "parent_step_id": llm3_id,
        "status": "success",
    })

    end_conversation(cid)
    print(f"  ✓ Conversation 4 done (1 round, ended)")


# ─────────────────────────────────────────────
# Conversation 5: API source, error scenario (ended)
# ─────────────────────────────────────────────
def seed_conv5():
    print("Creating conversation 5: error scenario via API...")
    conv = create_conversation("api_bot_test", "api")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "执行数据清洗脚本",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": False,
        "response_tool_calls": [
            {"id": "call_040", "type": "function", "function": {"name": "knowledge_search", "arguments": '{"query": "数据清洗脚本", "brief": "搜索数据清洗相关文档"}'}},
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 800,
        "output_tokens": 150,
        "total_tokens": 950,
        "duration_ms": 1100,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    # Tool call fails
    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "knowledge_search",
        "tool_type": "search",
        "tool_call_id": "call_040",
        "tool_arguments": {"query": "数据清洗脚本", "brief": "搜索数据清洗相关文档"},
        "tool_response": "Error: Knowledge base connection timeout after 30s",
        "brief": "搜索数据清洗相关文档",
        "parent_step_id": llm1_id,
        "status": "error",
        "error_message": "Knowledge base connection timeout",
    })

    # LLM handles error gracefully
    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": False,
        "content": "很抱歉，在搜索知识库时遇到了连接超时的问题。这可能是临时的网络波动，请稍后重试。如果问题持续，请联系管理员。",
        "finish_reason": "stop",
        "input_tokens": 1200,
        "output_tokens": 180,
        "total_tokens": 1380,
        "duration_ms": 1500,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "很抱歉，在搜索知识库时遇到了连接超时的问题。这可能是临时的网络波动，请稍后重试。如果问题持续，请联系管理员。",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    end_conversation(cid)
    print(f"  ✓ Conversation 5 done (1 round, has error, ended)")


# ─────────────────────────────────────────────
# Conversation 6: Simple single round, no tools (ended)
# ─────────────────────────────────────────────
def seed_conv6():
    print("Creating conversation 6: simple Q&A, no tools...")
    conv = create_conversation("user_wang_fang", "chat")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "你好，你能做什么？",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": True,
        "thinking_content": "用户在询问我的能力。我应该介绍我可以做的事情：搜索知识库、管理笔记、查询文档等。",
        "content": "你好！我是你的 AI 助手，主要可以帮你做以下事情：\n\n1. **知识检索**：搜索知识库中的文档和信息\n2. **文档查询**：查找和浏览文档目录\n3. **信息整理**：将重要信息记录到笔记中\n4. **数据分析**：简单的数据处理和分析\n\n有什么需要帮助的吗？",
        "finish_reason": "stop",
        "input_tokens": 600,
        "output_tokens": 250,
        "total_tokens": 850,
        "duration_ms": 1800,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "你好！我是你的 AI 助手，主要可以帮你做以下事情：\n\n1. **知识检索**：搜索知识库中的文档和信息\n2. **文档查询**：查找和浏览文档目录\n3. **信息整理**：将重要信息记录到笔记中\n4. **数据分析**：简单的数据处理和分析\n\n有什么需要帮助的吗？",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    end_conversation(cid)
    print(f"  ✓ Conversation 6 done (1 round, no tools, ended)")


# ─────────────────────────────────────────────
# Conversation 7: API batch, active
# ─────────────────────────────────────────────
def seed_conv7():
    print("Creating conversation 7: API batch, active...")
    conv = create_conversation("batch_service_v2", "api")
    if not conv:
        return
    cid = conv["id"]
    print(f"  conv_id={cid}, external_id={conv['external_id']}")

    create_step(cid, {
        "round_number": 1,
        "step_type": "user_message",
        "content": "查询文档 doc_102 的完整目录结构",
        "status": "success",
    })

    llm1 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": False,
        "response_tool_calls": [
            {"id": "call_050", "type": "function", "function": {"name": "doc_query", "arguments": '{"filter": {"doc_ids": ["doc_102"]}, "brief": "查询 doc_102 文档目录"}'}},
        ],
        "finish_reason": "tool_calls",
        "input_tokens": 700,
        "output_tokens": 120,
        "total_tokens": 820,
        "duration_ms": 900,
        "status": "success",
    })
    llm1_id = llm1["id"] if llm1 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "tool_call",
        "tool_name": "doc_query",
        "tool_type": "doc_query",
        "tool_call_id": "call_050",
        "tool_arguments": {"filter": {"doc_ids": ["doc_102"]}, "brief": "查询 doc_102 文档目录"},
        "tool_response": '<doc_query_results>\n<doc id="doc_102" title="退换货政策 v2.3" updated="2026-03-15" slices="28">\n<toc>\n1. 总则\n2. 通用退换货规定\n3. 电子产品退换货规定\n4. 服装类退换货规定\n5. 食品类退换货规定\n6. 附则\n</toc>\n</doc>\n</doc_query_results>',
        "brief": "查询 doc_102 文档目录",
        "parent_step_id": llm1_id,
        "status": "success",
    })

    llm2 = create_step(cid, {
        "round_number": 1,
        "step_type": "llm_call",
        "model_name": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "thinking_enabled": False,
        "content": "文档 **doc_102** — 《退换货政策 v2.3》的目录结构：\n\n1. 总则\n2. 通用退换货规定\n3. 电子产品退换货规定\n4. 服装类退换货规定\n5. 食品类退换货规定\n6. 附则\n\n共 28 个切片，最后更新于 2026-03-15。",
        "finish_reason": "stop",
        "input_tokens": 1100,
        "output_tokens": 200,
        "total_tokens": 1300,
        "duration_ms": 1600,
        "status": "success",
    })
    llm2_id = llm2["id"] if llm2 else None

    create_step(cid, {
        "round_number": 1,
        "step_type": "assistant_message",
        "content": "文档 **doc_102** — 《退换货政策 v2.3》的目录结构：\n\n1. 总则\n2. 通用退换货规定\n3. 电子产品退换货规定\n4. 服装类退换货规定\n5. 食品类退换货规定\n6. 附则\n\n共 28 个切片，最后更新于 2026-03-15。",
        "parent_step_id": llm2_id,
        "status": "success",
    })

    # Keep active
    print(f"  ✓ Conversation 7 done (1 round, API, ACTIVE)")


if __name__ == "__main__":
    print("=" * 50)
    print("Seeding test conversations...")
    print(f"Tenant: {TENANT_ID}, Agent: {AGENT_ID}")
    print("=" * 50)

    seed_conv1()
    print()
    seed_conv2()
    print()
    seed_conv3()
    print()
    seed_conv4()
    print()
    seed_conv5()
    print()
    seed_conv6()
    print()
    seed_conv7()

    print()
    print("=" * 50)
    print("All test data created successfully!")
    print("=" * 50)
