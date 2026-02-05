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