"""
Unit tests for Mustache-style template renderer.
"""
import pytest

from app.libs.template.renderer import render_template


class TestRenderTemplate:

    def test_simple_variable_replacement(self):
        result = render_template("Hello {{name}}!", {"name": "World"})
        assert result == "Hello World!"

    def test_missing_variable_becomes_empty(self):
        result = render_template("Hello {{name}}!", {})
        assert result == "Hello !"

    def test_conditional_block_with_value(self):
        tpl = "Start\n{{#first_search}}\n## Results\n\n{{.}}\n{{/first_search}}\nEnd"
        result = render_template(tpl, {"first_search": "some results"})
        assert "## Results" in result
        assert "some results" in result
        assert "Start" in result
        assert "End" in result

    def test_conditional_block_without_value(self):
        tpl = "Start\n{{#first_search}}\n## Results\n\n{{.}}\n{{/first_search}}\nEnd"
        result = render_template(tpl, {})
        assert "## Results" not in result
        assert "Start" in result
        assert "End" in result

    def test_conditional_block_empty_string(self):
        tpl = "Before\n{{#first_search}}\n## Search\n{{.}}\n{{/first_search}}\nAfter"
        result = render_template(tpl, {"first_search": ""})
        assert "## Search" not in result

    def test_dot_variable_in_block(self):
        tpl = "{{#first_search}}Content: {{.}}{{/first_search}}"
        result = render_template(tpl, {"first_search": "data"})
        assert result == "Content: data"

    def test_named_variable_in_block(self):
        tpl = "{{#first_search}}Content: {{first_search}}{{/first_search}}"
        result = render_template(tpl, {"first_search": "data"})
        assert result == "Content: data"

    def test_multiple_variables(self):
        tpl = "{{time}} - {{name}}"
        result = render_template(tpl, {"time": "now", "name": "bot"})
        assert result == "now - bot"

    def test_no_variables_passthrough(self):
        tpl = "Plain text with no variables"
        result = render_template(tpl, {})
        assert result == "Plain text with no variables"

    def test_excessive_newlines_cleaned(self):
        tpl = "A\n\n\n{{#x}}\nblock\n{{/x}}\n\n\nB"
        result = render_template(tpl, {})
        assert "\n\n\n" not in result

    def test_real_world_system_prompt(self):
        tpl = (
            "你是一个AI助手。\n\n"
            "{{#first_search}}\n"
            "## 搜索结果\n\n"
            "{{.}}\n"
            "{{/first_search}}\n\n"
            "请根据以上信息回答用户问题。"
        )
        result_with = render_template(tpl, {"first_search": "<result>data</result>"})
        assert "## 搜索结果" in result_with
        assert "<result>data</result>" in result_with

        result_without = render_template(tpl, {})
        assert "## 搜索结果" not in result_without
        assert "请根据以上信息回答用户问题" in result_without

    def test_datetime_variables(self):
        tpl = "今天是{{current_date}}，{{current_weekday}}，现在时间{{current_time}}，完整时间{{current_datetime}}"
        variables = {
            "current_date": "2026-04-14",
            "current_weekday": "星期二",
            "current_time": "15:30",
            "current_datetime": "2026-04-14 15:30",
        }
        result = render_template(tpl, variables)
        assert "2026-04-14" in result
        assert "星期二" in result
        assert "15:30" in result
        assert "2026-04-14 15:30" in result

    def test_datetime_variables_missing_fallback(self):
        tpl = "日期：{{current_date}} 星期：{{current_weekday}}"
        result = render_template(tpl, {})
        assert result == "日期： 星期："
