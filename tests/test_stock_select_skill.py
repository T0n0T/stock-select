import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / ".agents" / "skills" / "stock-select"


class StockSelectSkillTests(unittest.TestCase):
    def read_skill_files(self) -> str:
        files = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "cli-workflow.md",
            SKILL_ROOT / "references" / "runtime-layout.md",
            SKILL_ROOT / "references" / "youzi-subagent-review.md",
        ]
        for path in files:
            self.assertTrue(path.exists(), f"missing stock-select skill file: {path}")
        return "\n".join(path.read_text(encoding="utf-8") for path in files)

    def test_stock_select_skill_targets_current_cli_workspace(self):
        combined = self.read_skill_files()

        self.assertIn("/home/tiger/Documents/agents/stock-select", combined)
        self.assertIn("stock-select-rs run", combined)
        self.assertIn("--pick-date", combined)
        self.assertIn("--intraday", combined)
        self.assertIn("STOCK_SELECT_RUNTIME_ROOT", combined)
        self.assertIn("POSTGRES_DSN", combined)
        self.assertIn("TUSHARE_TOKEN", combined)
        self.assertNotIn("stock-select-new", combined)

    def test_stock_select_skill_documents_review_artifact_flow(self):
        combined = self.read_skill_files()

        required_terms = [
            "llm_tasks.json",
            "chart_path",
            "display.json",
            "factors.json",
            "ranked.json",
            "llm_annotations.json",
            "llm_raw",
            "review-merge",
            "llm_report.html",
            "KEEP",
            "CAUTION",
            "REJECT",
        ]
        for term in required_terms:
            self.assertIn(term, combined)

    def test_stock_select_skill_uses_youzi_review_without_old_prompt_files(self):
        combined = self.read_skill_files()

        self.assertIn("游资", combined)
        self.assertIn("龙虎榜", combined)
        self.assertIn("题材", combined)
        self.assertIn("情绪周期", combined)
        self.assertIn("连板", combined)
        self.assertIn("/home/tiger/Documents/agents/UZI-Skill", combined)
        self.assertNotIn("prompt-b1.md", combined)
        self.assertNotIn("prompt-b2.md", combined)
        self.assertNotIn("prompt-dribull.md", combined)

    def test_stock_select_skill_requires_real_subagent_spawn_for_llm_review(self):
        combined = self.read_skill_files()

        required_terms = [
            "真实 spawn",
            "每行一个子代理",
            "主 agent 不得代写",
            "agent_id",
            "并发",
        ]
        for term in required_terms:
            self.assertIn(term, combined)


if __name__ == "__main__":
    unittest.main()
