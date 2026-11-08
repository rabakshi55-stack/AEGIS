import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from joint_copilot import answer_joint
from tests.test_joint_copilot import fixture

class CopilotRoutingTests(unittest.TestCase):
    def test_explain_subtraction_not_repeat(self):
        a=answer_joint('How did you calculate the difference?',fixture())
        self.assertIn('subtract the optimized',a)
        self.assertIn('$230,037.00',a)
        self.assertNotIn('verified real savings',a)
    def test_reliability_cannot_be_inferred(self):
        for q in ('Which is the best supplier?', 'Which supplier has the lowest risk?', 'Who performs best?'):
            a=answer_joint(q,fixture())
            self.assertIn('does not establish supplier reliability',a)
            self.assertNotIn('SUP-014 is better',a)
    def test_next_step_specific_no_purchase_instruction(self):
        a=answer_joint('What next?',fixture())
        self.assertIn('confirm daily shared capacities',a)
        self.assertIn('Do not make a sourcing change',a)
    def test_elliptical_followup_uses_user_question_not_client_answer(self):
        a=answer_joint('Why?',fixture(),history=[{'question':'Should we switch suppliers?',
            'answer':'Unverified client assertion: supplier is guaranteed.'}])
        self.assertIn('existing commitments',a)
        self.assertNotIn('guaranteed',a)
    def test_elliptical_followup_without_context_does_not_create_facts(self):
        a=answer_joint('Why?',fixture(),history=[{'question':'How are you?'}])
        self.assertIn('synthetic',a)

if __name__=='__main__': unittest.main()
