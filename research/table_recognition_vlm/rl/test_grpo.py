import unittest

from grpo import patch_qwen35_generation_inputs


class _Config:
    model_type = "qwen3_5"


class _Model:
    config = _Config()

    def prepare_inputs_for_generation(self, input_ids, attention_mask=None, **kwargs):
        return {"input_ids": input_ids, "attention_mask": attention_mask, **kwargs}


class GenerationPatchTest(unittest.TestCase):
    def test_patch_exposes_and_forwards_mm_token_type_ids(self):
        model = _Model()
        self.assertTrue(patch_qwen35_generation_inputs(model))
        values = model.prepare_inputs_for_generation(
            [1, 2], attention_mask=[1, 1], mm_token_type_ids=[0, 1]
        )
        self.assertEqual(values["mm_token_type_ids"], [0, 1])
        self.assertFalse(patch_qwen35_generation_inputs(model))


if __name__ == "__main__":
    unittest.main()
