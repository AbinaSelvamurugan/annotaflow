"""Versioned, validated YAML configuration."""
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
import yaml


class Columns(BaseModel):
    id: str = "record_id"
    text: str = "text"
    label: str = "existing_label"
    source: str = "source"
    category: str = "category"


class DatasetConfig(BaseModel):
    path: str
    format: str = "auto"
    encoding: str = "utf-8"
    columns: Columns = Field(default_factory=Columns)
    required: list[str] = Field(default_factory=lambda: ["text"])
    allowed_sources: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    auto_generate_ids: bool = True
    min_text_chars: int = Field(default=3, ge=1)
    version: str = "v1"


class AnnotationConfig(BaseModel):
    version: str
    project_title: str
    labels: list[str] = Field(min_length=2)
    label_descriptions: dict[str, str]
    result_from_name: str = "sentiment"
    result_to_name: str = "text"
    require_two_annotators: bool = True

    @model_validator(mode="after")
    def valid_labels(self):
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("Annotation labels must be unique")
        if set(self.label_descriptions) != set(self.labels):
            raise ValueError("Each annotation label must have exactly one description")
        return self


class QualityConfig(BaseModel):
    near_duplicates: bool = True
    near_duplicate_threshold: float = Field(default=0.90, gt=0, le=1)
    near_duplicate_max_rows: int = Field(default=3000, ge=1)
    ci_bootstrap_iterations: int = Field(default=0, ge=0)
    review_group_agreement_below: float = Field(default=0.65, ge=0, le=1)
    min_group_pairs: int = Field(default=10, ge=2)


class CleaningConfig(BaseModel):
    normalize_whitespace: bool = True
    label_aliases: dict[str, str] = Field(default_factory=dict)
    duplicate_key: list[str] = Field(default_factory=lambda: ["text"])
    duplicate_policy: str = "exclude_identical"
    exclude_invalid: bool = True
    exclude_unresolved: bool = False

    @model_validator(mode="after")
    def valid_policy(self):
        if self.duplicate_policy not in {"exclude_identical", "review_only"}:
            raise ValueError("Invalid duplicate_policy")
        if not set(self.duplicate_key) <= {"text", "source", "category"}:
            raise ValueError("duplicate_key may use text, source or category")
        return self


class Config(BaseModel):
    dataset: DatasetConfig
    annotation: AnnotationConfig
    quality: QualityConfig
    cleaning: CleaningConfig

    @model_validator(mode="after")
    def aliases(self):
        if not set(self.cleaning.label_aliases.values()) <= set(self.annotation.labels):
            raise ValueError("Label aliases must map to existing canonical labels")
        return self


def load_config(root: Path) -> Config:
    def read(name):
        with (root / "configs" / f"{name}.yaml").open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    return Config(dataset=read("dataset"), annotation=read("annotation"),
                  quality=read("quality"), cleaning=read("cleaning"))
