from __future__ import annotations

from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator


VarType = Literal["stock", "aux", "param"]


class Bounds(BaseModel):
    min: float
    max: float

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min > self.max:
            raise ValueError(f"bounds.min ({self.min}) cannot be > bounds.max ({self.max})")
        return self


class Variable(BaseModel):
    id: str
    name: str
    type: VarType
    unit: str
    description: Optional[str] = ""

    bounds: Optional[Bounds] = None

    # Only for stock
    initial: Optional[float] = None

    # Only for param
    default: Optional[float] = None

    @model_validator(mode="after")
    def check_required_by_type(self):
        if self.type == "stock" and self.initial is None:
            raise ValueError(f"Variable '{self.id}' is a stock but has no 'initial'")
        if self.type == "param" and self.default is None:
            raise ValueError(f"Variable '{self.id}' is a param but has no 'default'")
        return self


class VariablesConfig(BaseModel):
    variables: List[Variable]


class Scenario(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    knobs: Dict[str, float] = Field(default_factory=dict)


class ScenariosConfig(BaseModel):
    scenarios: List[Scenario]


class ModelCore(BaseModel):
    time_step_months: int = 1
    horizon_years: int = 10
    parameters: Dict[str, float] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    model: ModelCore


class RecThresholds(BaseModel):
    # If any of these are violated => downgrade decision
    min_deals_won_per_year: float = 2.0
    min_reputation: float = 0.35
    max_constraints: float = 0.80
    min_market_access: float = 0.20


class RecommendationRule(BaseModel):
    id: str
    description: str = ""
    thresholds: RecThresholds


class RecommendationRulesConfig(BaseModel):
    recommendation_rules: List[RecommendationRule]


# =========================================================
# NEW (for Model Transparency): Evidence + Assumptions
# These are additive and will NOT affect existing validators.
# =========================================================

Reliability = Literal["A", "B", "C", "D"]
EvidenceSourceType = Literal["policy", "paper", "internal", "news", "other"]
Uncertainty = Literal["low", "medium", "high"]


class EvidenceItem(BaseModel):
    id: str
    source_type: EvidenceSourceType
    title: str
    snippet: str
    reliability: Reliability

    jurisdiction: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class EvidenceConfig(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate evidence ids found in evidence.yaml")
        return self


class AssumptionItem(BaseModel):
    id: str
    statement: str
    uncertainty: Uncertainty

    owner: Optional[str] = None
    review_date: Optional[str] = None

    linked_variables: List[str] = Field(default_factory=list)
    linked_params: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)

    notes: Optional[str] = None


class AssumptionsConfig(BaseModel):
    assumptions: List[AssumptionItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [a.id for a in self.assumptions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate assumption ids found in assumptions.yaml")
        return self