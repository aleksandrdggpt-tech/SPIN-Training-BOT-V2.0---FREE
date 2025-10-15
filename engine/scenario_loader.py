import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class LoadedScenario:
    """Container for a loaded scenario configuration."""
    path: Path
    config: Dict[str, Any]


class ScenarioValidationError(Exception):
    """Raised when scenario configuration validation fails."""


class ScenarioLoader:
    """Loads and validates scenario configurations and provides helpers to access texts.

    Expected JSON structure is documented in `scenarios/template/config.json`.
    """

    def __init__(self) -> None:
        self._loaded: Optional[LoadedScenario] = None

    def load_scenario(self, scenario_path: str) -> LoadedScenario:
        """Load scenario JSON from path and validate structure.

        Args:
            scenario_path: Path to the JSON config file
        Returns:
            LoadedScenario
        Raises:
            FileNotFoundError, json.JSONDecodeError, ScenarioValidationError
        """
        path = Path(scenario_path).expanduser().resolve()
        logger.info("Loading scenario config from %s", path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario config not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)

        self.validate_config(config)
        # Optional deep validation for case variants if present
        if 'case_variants' in config:
            self._validate_case_variants(config['case_variants'])
        self._loaded = LoadedScenario(path=path, config=config)
        logger.info("Scenario loaded: %s v%s", config.get("scenario_info", {}).get("name"), config.get("scenario_info", {}).get("version"))
        return self._loaded

    def validate_config(self, config: Dict[str, Any]) -> None:
        """Validate basic structure of the configuration dictionary.

        Raises:
            ScenarioValidationError if required keys or types are missing.
        """
        required_top = ["scenario_info", "messages", "prompts", "question_types", "game_rules", "scoring", "ui"]
        for key in required_top:
            if key not in config:
                raise ScenarioValidationError(f"Missing required section: {key}")

        # Minimal checks for nested structures
        if not isinstance(config["question_types"], list) or not config["question_types"]:
            raise ScenarioValidationError("question_types must be a non-empty list")

        info = config.get("scenario_info", {})
        for k in ["name", "version", "description"]:
            if k not in info:
                raise ScenarioValidationError(f"scenario_info.{k} is required")

        messages = config.get("messages", {})
        for k in ["welcome", "case_generated", "training_complete", "error_generic"]:
            if k not in messages:
                raise ScenarioValidationError(f"messages.{k} is required")

        prompts = config.get("prompts", {})
        for k in ["case_generation", "client_response", "feedback"]:
            if k not in prompts:
                raise ScenarioValidationError(f"prompts.{k} is required")

        game_rules = config.get("game_rules", {})
        for k in ["max_questions", "min_questions_for_completion", "target_clarity", "short_question_threshold"]:
            if k not in game_rules:
                raise ScenarioValidationError(f"game_rules.{k} is required")

        scoring = config.get("scoring", {})
        if "badges" not in scoring or not isinstance(scoring["badges"], list):
            raise ScenarioValidationError("scoring.badges must be a list")

        ui = config.get("ui", {})
        for k in ["progress_format", "commands"]:
            if k not in ui:
                raise ScenarioValidationError(f"ui.{k} is required")

    def _validate_case_variants(self, variants: Dict[str, Any]) -> None:
        """Validate the optional case_variants section."""
        # positions or positions_by_size acceptable
        required_keys = ['companies', 'company_sizes', 'regions', 'products', 'base_situations']
        for key in required_keys:
            if key not in variants:
                raise ScenarioValidationError(f"Missing required key in case_variants: {key}")
            if not variants[key]:
                raise ScenarioValidationError(f"Empty list in case_variants.{key}")

        if ('positions' not in variants) and ('positions_by_size' not in variants):
            raise ScenarioValidationError("case_variants must contain either 'positions' or 'positions_by_size'")

        for product in variants.get('products', []):
            if 'name' not in product:
                raise ScenarioValidationError(f"Product missing 'name': {product}")
            if 'unit' not in product:
                logger.warning("Product %s missing 'unit', default will be used", product.get('name', '<unknown>'))

        for situation in variants.get('base_situations', []):
            if 'type' not in situation or 'template' not in situation:
                raise ScenarioValidationError(f"Base situation missing required fields: {situation}")
        logger.info("✅ Валидация case_variants пройдена успешно")

    def _ensure_loaded(self) -> LoadedScenario:
        if not self._loaded:
            raise RuntimeError("Scenario not loaded. Call load_scenario() first.")
        return self._loaded

    def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """Get a prompt by name and format with kwargs."""
        loaded = self._ensure_loaded()
        template = loaded.config["prompts"].get(prompt_name)
        if template is None:
            raise KeyError(f"Prompt not found: {prompt_name}")
        return str(template).format(**kwargs)

    def get_message(self, message_name: str, **kwargs: Any) -> str:
        """Get a message by name and format with kwargs."""
        loaded = self._ensure_loaded()
        template = loaded.config["messages"].get(message_name)
        if template is None:
            raise KeyError(f"Message not found: {message_name}")
        return str(template).format(**kwargs)


