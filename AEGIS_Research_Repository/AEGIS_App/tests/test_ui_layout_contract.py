"""Offline layout regressions: no browser or external services required."""
from pathlib import Path
import unittest

WEB = Path(__file__).resolve().parents[1] / "web"


class LayoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.styles = (WEB / "styles.css").read_text(encoding="utf-8")
        cls.markup = (WEB / "index.html").read_text(encoding="utf-8")
        cls.script = (WEB / "app.js").read_text(encoding="utf-8")

    def test_chart_recommendation_panel_has_inner_padding_and_wrapping(self):
        self.assertIn(".chart-goal-panel { padding: 24px", self.styles)
        self.assertIn(".chart-goal-form textarea { width: 100%", self.styles)
        self.assertIn('id="chart-goal-question"', self.markup)

    def test_adaptive_chart_actions_stay_in_one_responsive_group(self):
        self.assertIn('class="adaptive-card-actions"', self.script)
        self.assertIn(".adaptive-card-actions {", self.styles)
        self.assertIn(".adaptive-card-actions .secondary-action {", self.styles)
        self.assertIn('data-adaptive-customize="${html(spec.id)}"', self.script)
        self.assertIn('data-adaptive-ask="${html(spec.id)}"', self.script)

    def test_long_dataset_and_chat_text_have_safe_wrapping(self):
        for text in ("#viz-filename", "#intake-filename", ".chat-bubble", ".custom-chart-axis"):
            self.assertIn(text, self.styles)
        self.assertIn("overflow-wrap: anywhere", self.styles)
        self.assertIn(".chat-heading { flex-wrap: wrap", self.styles)

    def test_offscreen_drawer_does_not_break_viewport_layout(self):
        self.assertIn('detail-drawer[aria-hidden="true"]', self.styles)
        self.assertIn("html, body { overflow-x: clip; }", self.styles)
        self.assertIn("@media (max-width: 440px)", self.styles)


if __name__ == "__main__":
    unittest.main()
