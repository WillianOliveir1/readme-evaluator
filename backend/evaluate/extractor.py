"""Evaluation utilities: extract structured JSON from README text using prompts + LLM."""
from __future__ import annotations

import json
import time
from typing import Optional, Any, Dict, Callable
import jsonschema

from backend import prompt_builder
from backend.gemini_client import GeminiClient
from backend.evaluate.progress import ProgressTracker, ProgressStage, EvaluationResult
from backend.evaluate.json_postprocessor import fix_string_arrays_in_json, remove_disallowed_category_fields
import logging

logger = logging.getLogger(__name__)


def extract_json_from_readme(
    readme_text: str,
    schema_path: str,
    example_json: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    readme_path: Optional[str] = None,
    max_tokens: int = 20480,
    temperature: float = 0.0,
    progress_callback: Optional[Callable] = None,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    readme_raw_link: Optional[str] = None,
) -> EvaluationResult:
    """Build extraction prompt and call model (if model provided).

    Returns an EvaluationResult with:
      - prompt: the built prompt string
      - model_output: raw model response (if model provided)
      - parsed: parsed JSON object if output was valid JSON, else None
      - progress_history: list of ProgressUpdate objects
      - timing: dict with timing information
      - tokens: dict with token usage
    """
    # Initialize progress tracker
    tracker = ProgressTracker(callback=progress_callback)
    timing = {}
    
    try:
        # Stage 1: Building Prompt
        tracker.start_stage(ProgressStage.BUILDING_PROMPT, "Loading schema and building prompt...")
        build_start = time.time()
        
        schema_text = prompt_builder.PromptBuilder.load_schema_text(schema_path)
        # Try to parse the schema text into a JSON object for validation later
        schema_obj = None
        try:
            schema_obj = __import__("json").loads(schema_text) if schema_text else None
        except Exception:
            schema_obj = None

        # Log diagnostics
        try:
            logging.info("extract_json_from_readme: readme_text length=%d", len(readme_text) if readme_text is not None else 0)
            if readme_text:
                logging.debug("extract_json_from_readme: readme_text snippet: %s", readme_text[:400].replace('\n', ' '))
        except Exception:
            pass

        # Build prompt using PromptBuilder
        pb = prompt_builder.PromptBuilder(template_header=system_prompt or None, schema=schema_text, readme=readme_text)
        
        # Add repository context for metadata population
        if owner or repo or readme_raw_link:
            repo_context = "REPOSITORY CONTEXT (fill these fields in the JSON metadata):\n"
            if owner:
                repo_context += f"- Repository Owner: {owner}\n"
            if repo:
                repo_context += f"- Repository Name: {repo}\n"
            if owner and repo:
                repo_context += f"- Repository Link: https://github.com/{owner}/{repo}\n"
            if readme_raw_link:
                repo_context += f"- README Raw Link: {readme_raw_link}\n"
            if model:
                repo_context += f"- Evaluator Model: {model}\n"
            pb.add_part("repository_context", repo_context)
        
        if readme_path:
            try:
                pb.add_part("readme_path", readme_path)
            except Exception:
                pass
        
        if example_json is not None:
            try:
                example_str = json.dumps(example_json, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                example_str = str(example_json)
            pb.add_part("example_json", example_str)

        footer = (
            "IMPORTANT: The model must output a single JSON object, valid according to the schema above. "
            "No surrounding backticks, no markdown, no commentary."
        )

        prompt = pb.build(instruction=None, footer=footer)
        timing["prompt_build"] = time.time() - build_start
        
        # Log prompt info
        try:
            snippet = prompt[:1000].replace('\n', ' ') if prompt else ''
            logger.info("extractor: built prompt length=%d", len(prompt))
        except Exception:
            logger.exception("extractor: failed to log prompt preview")

        tracker.complete_stage(ProgressStage.BUILDING_PROMPT, f"Prompt built ({len(prompt)} chars)")
        
        # Create result object
        result_obj = EvaluationResult(
            success=True,
            prompt=prompt,
            timing=timing,
        )

        # Stage 2: Call Model (if provided)
        if model:
            tracker.start_stage(ProgressStage.CALLING_MODEL, f"Calling {model}...")
            model_start = time.time()
            
            try:
                client = GeminiClient()
                
                # Streaming implementation
                full_response = []
                stream = client.generate_stream(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
                
                for chunk in stream:
                    full_response.append(chunk)
                    # Update progress with current length
                    current_len = sum(len(c) for c in full_response)
                    tracker.update_stage(
                        ProgressStage.CALLING_MODEL, 
                        f"Generating response... ({current_len} chars)"
                    )
                
                raw = "".join(full_response)
                
                result_obj.model_output = raw
                timing["model_call"] = time.time() - model_start
                
                if not raw or not raw.strip():
                    # Empty response from model
                    tracker.error_stage(ProgressStage.CALLING_MODEL, "Empty response from model", "Model returned empty output")
                    tracker.start_stage(ProgressStage.PARSING_JSON, "JSON parsing skipped (empty model output)")
                    tracker.complete_stage(ProgressStage.PARSING_JSON, "JSON parsing skipped")
                    tracker.start_stage(ProgressStage.VALIDATING, "Validation skipped (no parsed JSON)")
                    tracker.complete_stage(ProgressStage.VALIDATING, "Validation skipped")
                    result_obj.recovery_suggestions.append("Model returned empty response. Check API key, rate limits, or try again.")
                else:
                    tracker.complete_stage(
                        ProgressStage.CALLING_MODEL,
                        f"Model responded ({len(raw)} chars)",
                        details={"response_length": len(raw)}
                    )
                    
                    # Stage 3: Parse JSON
                    tracker.start_stage(ProgressStage.PARSING_JSON, "Parsing JSON response...")
                    parse_start = time.time()
                    
                    try:
                        # Remove markdown backticks if present
                        raw_cleaned = raw.strip()
                        if raw_cleaned.startswith("```json"):
                            raw_cleaned = raw_cleaned[7:]
                        elif raw_cleaned.startswith("```"):
                            raw_cleaned = raw_cleaned[3:]
                        
                        if raw_cleaned.endswith("```"):
                            raw_cleaned = raw_cleaned[:-3]
                        
                        raw_cleaned = raw_cleaned.strip()
                        
                        # Parse JSON
                        parsed = json.loads(raw_cleaned)
                        
                        # Apply post-processing to fix string → array conversions
                        parsed = fix_string_arrays_in_json(parsed)
                        
                        # Remove fields not allowed in specific categories
                        parsed = remove_disallowed_category_fields(parsed)
                        
                        result_obj.parsed = parsed
                        timing["parsing"] = time.time() - parse_start
                        tracker.complete_stage(ProgressStage.PARSING_JSON, "JSON parsed and fixed successfully")
                        
                        # POST-PROCESS: Ensure repository metadata is correctly populated
                        # The model receives context but may not fill these correctly, so we enforce them
                        if result_obj.parsed and isinstance(result_obj.parsed, dict):
                            if "metadata" not in result_obj.parsed:
                                result_obj.parsed["metadata"] = {}
                            
                            metadata = result_obj.parsed["metadata"]
                            
                            # repository_owner: Add if we have it and it's missing or N/A
                            if owner:
                                current = metadata.get("repository_owner", "")
                                if not current or current == "N/A":
                                    metadata["repository_owner"] = owner
                                    logging.info(f"Filled repository_owner: {owner}")
                            
                            # repository_name: Add if we have it and it's missing or N/A
                            if repo:
                                current = metadata.get("repository_name", "")
                                if not current or current == "N/A":
                                    metadata["repository_name"] = repo
                                    logging.info(f"Filled repository_name: {repo}")
                            
                            # repository_link: Construct from owner/repo if missing or N/A
                            if owner and repo:
                                expected_link = f"https://github.com/{owner}/{repo}"
                                current = metadata.get("repository_link", "")
                                if not current or current == "N/A":
                                    metadata["repository_link"] = expected_link
                                    logging.info(f"Filled repository_link: {expected_link}")
                            
                            # readme_raw_link: Add if we have it and it's missing or N/A
                            if readme_raw_link:
                                current = metadata.get("readme_raw_link", "")
                                if not current or current == "N/A":
                                    metadata["readme_raw_link"] = readme_raw_link
                                    logging.info(f"Filled readme_raw_link: {readme_raw_link}")
                            
                            # evaluation_date: ALWAYS set to current UTC date in ISO format
                            from datetime import datetime
                            current_date = datetime.utcnow().strftime("%Y-%m-%d")
                            metadata["evaluation_date"] = current_date
                            logging.info(f"Set evaluation_date to: {current_date}")
                            
                            # evaluator: ALWAYS use the model name (model doesn't know its own name)
                            if model:
                                metadata["evaluator"] = model
                                logging.info(f"Set evaluator to model: {model}")
                    except json.JSONDecodeError as e:
                        result_obj.parsed = None
                        timing["parsing"] = time.time() - parse_start
                        logger.error("JSON decode error: %s, raw length: %d, raw snippet: %s", str(e), len(raw), raw[:200])
                        tracker.error_stage(ProgressStage.PARSING_JSON, str(e), "Failed to parse JSON")
                        result_obj.recovery_suggestions.append("Model output was not valid JSON. Try with a different model or adjust temperature.")

                    # Stage 4: Validate
                    if result_obj.parsed is not None:
                        tracker.start_stage(ProgressStage.VALIDATING, "Validating against schema...")
                        validate_start = time.time()
                        
                        if schema_obj is not None:
                            try:
                                jsonschema.validate(instance=result_obj.parsed, schema=schema_obj)
                                result_obj.validation_ok = True
                                result_obj.validation_errors = None
                                timing["validation"] = time.time() - validate_start
                                tracker.complete_stage(ProgressStage.VALIDATING, "Schema validation passed")
                            except jsonschema.ValidationError as ve:
                                result_obj.validation_ok = False
                                try:
                                    err_path = list(ve.path)
                                except Exception:
                                    err_path = []
                                result_obj.validation_errors = {
                                    "message": str(ve.message),
                                    "path": err_path,
                                }
                                timing["validation"] = time.time() - validate_start
                                tracker.error_stage(
                                    ProgressStage.VALIDATING,
                                    f"Schema validation failed at {err_path}",
                                    message="Schema validation failed"
                                )
                                result_obj.recovery_suggestions.append(f"Field validation failed at: {'.'.join(map(str, err_path))}")
                        else:
                            result_obj.validation_ok = None
                            result_obj.validation_errors = None
                    else:
                        tracker.start_stage(ProgressStage.VALIDATING, "Validation skipped (no valid JSON)")
                        tracker.complete_stage(ProgressStage.VALIDATING, "Validation skipped")
                
            except Exception as e:
                logger.exception("Model call error: %s", str(e))
                tracker.error_stage(ProgressStage.CALLING_MODEL, str(e), f"Error calling model: {type(e).__name__}")
                result_obj.recovery_suggestions.append(f"Model call failed: {str(e)}")
        else:
            # No model provided - skip calling model and parsing
            tracker.start_stage(ProgressStage.CALLING_MODEL, "Model call skipped (not requested)")
            tracker.complete_stage(ProgressStage.CALLING_MODEL, "Model call skipped")
            tracker.start_stage(ProgressStage.PARSING_JSON, "JSON parsing skipped (no model output)")
            tracker.complete_stage(ProgressStage.PARSING_JSON, "JSON parsing skipped")
            tracker.start_stage(ProgressStage.VALIDATING, "Validation skipped (no parsed JSON)")
            tracker.complete_stage(ProgressStage.VALIDATING, "Validation skipped")
        
        
        timing["total"] = time.time() - tracker.start_time
        result_obj.timing = timing
        result_obj.progress_history = tracker.get_history()
        tracker.complete_stage(ProgressStage.COMPLETED, "Evaluation completed")
        
        return result_obj
        
    except Exception as e:
        logger.exception("Unexpected error in extract_json_from_readme")
        return EvaluationResult(
            success=False,
            prompt="",
            progress_history=tracker.get_history(),
            timing=timing,
            recovery_suggestions=[f"Unexpected error: {str(e)}"],
        )

