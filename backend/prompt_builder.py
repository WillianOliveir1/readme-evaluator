import json
import textwrap
from typing import Optional, List, Tuple


class PromptBuilder:
    """Composable prompt builder that accepts N named parts and renders a single prompt string.

    Usage:
      pb = PromptBuilder(template_header="You are a JSON extraction assistant.")
      pb.add_part("SCHEMA", schema_text)
      pb.add_part("README", readme_text)
      prompt = pb.build(instruction=...)

    The builder will prefix each part with the provided name (keeps names as provided). It keeps order
    of insertion and formats the final prompt with a conservative instruction section.
    """

    def __init__(self, template_header: Optional[str] = None, *args, **kwargs):
        """Initialize the PromptBuilder.

        Recommended usage: pass named parts as keyword args so the variable name is used as the
        label, e.g. PromptBuilder(schema=schema_text, readme=readme_text). Positional args are
        accepted but will be labeled PART_1, PART_2, ... (no name inference).
        """
        self.template_header = template_header or "You are a JSON extraction assistant."
        self.parts: List[Tuple[str, str]] = []

        # Add kwargs first: keys are used as labels
        for k, v in kwargs.items():
            try:
                text = v if isinstance(v, str) else str(v)
            except Exception:
                text = ""
            self.add_part(k, text)

        # Positional args: add with fallback labels PART_1, PART_2, ...
        for i, value in enumerate(args):
            label = f"PART_{i+1}"
            try:
                text = value if isinstance(value, str) else str(value)
            except Exception:
                text = ""
            self.add_part(label, text)

    @staticmethod
    def load_schema_text(schema_path: str) -> str:
        """Return the raw JSON Schema text (keeps formatting) so it can be embedded in prompts."""
        with open(schema_path, "r", encoding="utf-8") as f:
            return f.read()

    def add_part(self, name: str, text: str) -> None:
        """Add a named part to the prompt. Name will be used as a label before the text.

        Example: add_part('README', 'L0001: ...')
        """
        label = name.strip()
        self.parts.append((label, text))

    def extend_parts(self, items: List[Tuple[str, str]]) -> None:
        """Add multiple named parts preserving order.

        items: list of (name, text)
        """
        for name, text in items:
            self.add_part(name, text)

    def _infer_names_for_positional_args(self, n: int) -> List[Optional[str]]:
        # Name inference removed; prefer passing named kwargs so labels are explicit.
        raise NotImplementedError("_infer_names_for_positional_args is not supported; pass named kwargs instead")

    def build(self, instruction: Optional[str] = None, footer: Optional[str] = None) -> str:
        """Compose the final prompt.

        - instruction: short instruction text placed after the header.
        - footer: appended after all parts (e.g., output constraints).
        """
        instruction = (
            instruction
            or "Extract the information from the README and return a single JSON object that matches the supplied JSON Schema exactly. Do not include any explanatory text. Return only a valid JSON object."
        )

        parts: List[str] = [self.template_header, "INSTRUCTIONS:", instruction, ""]

        for label, text in self.parts:
            parts.append(f"{label}:")
            parts.append(text)
            parts.append("")

        if footer:
            parts.append(footer)
        else:
            parts.append(
                "IMPORTANT: The model must output a single JSON object, valid according to the schema above. No surrounding backticks, no markdown, no commentary."
            )

        prompt = "\n".join(parts)
        return textwrap.dedent(prompt)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.build())


# Backwards-compatible helper functions
    # Note: top-level compatibility helper functions were removed to prefer the class API.
    # Use PromptBuilder.load_schema_text(...) and PromptBuilder(...).build(...) instead.


if __name__ == "__main__":
    # tiny demo when executed directly
    import sys

    if len(sys.argv) < 3:
        print("Usage: prompt_builder.py <schema.json> <readme.md> [example.json]")
        sys.exit(2)

    schema = PromptBuilder.load_schema_text(sys.argv[1])
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        readme = f.read()

    example = None
    if len(sys.argv) >= 4:
        with open(sys.argv[3], "r", encoding="utf-8") as f:
            example = json.load(f)

    pb = PromptBuilder(schema=schema, readme=readme)
    if example is not None:
        try:
            ex_text = json.dumps(example, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            ex_text = str(example)
        pb.add_part("example_json", ex_text)

    prompt = pb.build()
    print(prompt[:4000])
