from __future__ import annotations

from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from pydantic import field_validator

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
    source_type: str
    title: str
    snippet: str
    reliability: str
    jurisdiction: Optional[str] = ""
    date: Optional[str] = ""          # keep it as string in the model output
    url: Optional[str] = ""
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = ""

    @field_validator("date", mode="before")
    def coerce_date_to_string(cls, v):
        # PyYAML may parse YYYY-MM-DD into datetime.date
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v


class EvidenceConfig(BaseModel):
    evidence: List[EvidenceItem]




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
    

# =========================================================
# NEW: configs/claims.yaml
# =========================================================
from typing import Literal
from pydantic import Field

ClaimStatus = Literal["proposed", "approved", "rejected"]
Polarity = Literal["+", "-"]


class ClaimItem(BaseModel):
    id: str
    status: ClaimStatus = "proposed"
    statement: str

    from_var: str
    to_var: str
    polarity: Polarity = "+"

    delay_months: int = Field(default=0, ge=0, le=120)

    evidence_id: str
    evidence_snippet: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    reviewer_note: str = ""


class ClaimsConfig(BaseModel):
    claims: List[ClaimItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [c.id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate claim ids found in claims.yaml")
        return self


# -----------------------------
# Step 3/4: Claims + Loops
# -----------------------------
from typing import Literal as _Literal  # keep file safe if you already imported Literal above


ClaimStatus = _Literal["proposed", "approved", "rejected"]
ClaimPolarity = _Literal["+", "-"]


class Claim(BaseModel):
    id: str
    status: ClaimStatus = "proposed"
    statement: str = ""
    from_var: str
    to_var: str
    polarity: ClaimPolarity = "+"
    delay_months: int = 0
    confidence: float = 0.6

    # evidence (optional)
    evidence_id: Optional[str] = None
    evidence_snippet: Optional[str] = None
    notes: Optional[str] = ""

    @model_validator(mode="after")
    def check_claim(self):
        if self.delay_months < 0:
            raise ValueError("delay_months must be >= 0")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        return self


class ClaimsConfig(BaseModel):
    claims: List[Claim]


LoopType = _Literal["R", "B"]


class Loop(BaseModel):
    id: str
    type: LoopType
    sign: int
    nodes: List[str]
    edge_claim_ids: List[str]
    notes: Optional[str] = ""


class LoopsConfig(BaseModel):
    loops: List[Loop]