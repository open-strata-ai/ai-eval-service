from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Split(str, Enum):
    train = "train"
    eval = "eval"
    test = "test"


class DatasetSource(str, Enum):
    human = "human"
    synthetic = "synthetic"
    online_sample = "online_sample"
    badcase = "badcase"


class EvalCase(BaseModel):
    case_id: str = Field(default_factory=lambda: f"case-{uuid.uuid4().hex[:12]}")
    inputs: dict = Field(default_factory=dict)
    expected: Optional[dict] = None
    contexts: Optional[list] = None
    tags: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    dataset_id: str
    name: str
    version: str = "v1"
    split: Split = Split.eval
    source: DatasetSource = DatasetSource.human
    cases: list[EvalCase] = Field(default_factory=list)
    dist_meta: dict = Field(default_factory=dict)
    tenant_id: str = "local"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_case(self, case: EvalCase) -> None:
        self.cases.append(case)

    def bump_version(self) -> str:
        # Semantic patch bump (docking §6.4 version management).
        if self.version.startswith("v"):
            prefix, num = "v", self.version[1:]
        else:
            prefix, num = "", self.version
        parts = num.split(".")
        if len(parts) == 1:
            parts = [parts[0], "0", "0"]
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError:
            parts = ["1", "0", "0"]
        self.version = prefix + ".".join(parts)
        return self.version

    def distribution(self) -> dict:
        by_tag: dict[str, int] = {}
        for c in self.cases:
            for t in c.tags:
                by_tag[t] = by_tag.get(t, 0) + 1
        avg = (
            sum(len(str(c.inputs)) for c in self.cases) / len(self.cases)
            if self.cases
            else 0.0
        )
        return {"case_count": len(self.cases), "by_tag": by_tag, "avg_input_len": avg}
