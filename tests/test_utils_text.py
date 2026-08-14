import unittest

from utils.text import count_tokens, estimate_tokens, truncate_text

SUFFIX = "\n...[truncated]"


class EstimateTokensTests(unittest.TestCase):
    def test_counts_roughly_four_characters_per_token(self):
        self.assertEqual(estimate_tokens("a" * 400), 100)

    def test_never_returns_zero(self):
        # The floor exists so a caller budgeting against it cannot divide by or
        # compare against 0 for a short-but-present string.
        self.assertEqual(estimate_tokens(""), 1)
        self.assertEqual(estimate_tokens("abc"), 1)


class CountTokensTests(unittest.TestCase):
    def test_empty_text_costs_nothing(self):
        self.assertEqual(count_tokens(""), 0)

    def test_longer_text_never_costs_less(self):
        short = count_tokens("hello")
        longer = count_tokens("hello world, this is a longer sentence")
        self.assertGreater(longer, short)

    def test_an_unknown_model_still_counts(self):
        # get_tokenizer falls back to cl100k_base rather than raising, so a model
        # name the tokenizer has never heard of must not break a count.
        self.assertEqual(count_tokens("hello world", "not-a-real-model-xyz"), count_tokens("hello world"))


class TruncateTextTests(unittest.TestCase):
    def test_text_within_budget_is_returned_untouched(self):
        text = "one\ntwo\nthree"
        self.assertEqual(truncate_text(text, "", 1000), text)
        self.assertNotIn("truncated", truncate_text(text, "", 1000))

    def test_the_result_fits_the_budget(self):
        text = "line of text\n" * 200
        for budget in (20, 50, 120):
            with self.subTest(budget=budget):
                out = truncate_text(text, "", budget)
                self.assertLessEqual(count_tokens(out), budget)

    def test_a_truncated_result_says_so(self):
        out = truncate_text("line of text\n" * 200, "", 30)
        self.assertTrue(out.endswith(SUFFIX))

    def test_line_mode_cuts_on_a_line_boundary(self):
        text = "".join(f"line {i}\n" for i in range(200))
        out = truncate_text(text, "", 40, preserve_lines=True)
        body = out[: -len(SUFFIX)]
        # Every line kept is a whole line from the input, in order.
        kept = body.split("\n")
        self.assertTrue(all(line == f"line {i}" for i, line in enumerate(kept)))

    def test_char_mode_fits_the_budget_too(self):
        text = "a very long single line without any newline in it " * 100
        out = truncate_text(text, "", 25, preserve_lines=False)
        self.assertLessEqual(count_tokens(out), 25)
        self.assertTrue(out.endswith(SUFFIX))

    def test_line_mode_falls_back_to_characters_when_no_whole_line_fits(self):
        # One line far larger than the budget: keeping whole lines would return
        # nothing, so the character path has to take over.
        text = "x" * 4000
        out = truncate_text(text, "", 12, preserve_lines=True)
        self.assertLessEqual(count_tokens(out), 12)
        self.assertTrue(out.endswith(SUFFIX))
        self.assertGreater(len(out), len(SUFFIX))

    def test_a_budget_smaller_than_the_suffix_yields_just_the_suffix(self):
        out = truncate_text("some long text " * 100, "", 1)
        self.assertEqual(out, SUFFIX.strip())

    def test_a_custom_suffix_is_used(self):
        out = truncate_text("line\n" * 200, "", 30, suffix=" [cut]")
        self.assertTrue(out.endswith(" [cut]"))


if __name__ == "__main__":
    unittest.main()
