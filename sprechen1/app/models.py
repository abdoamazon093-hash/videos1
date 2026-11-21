from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ReplacementItem(BaseModel):
    wrong_or_arabic: str
    right_german: str
    why_replaced: str
    example: Optional[str] = ""

class RadarRule(BaseModel):
    segment: str
    level: str
    rule_name: str
    explanation: str
    examples: List[Dict[str, str]] = []

class CorrectionRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to correct")
    lang_mode: Optional[str] = "de"
    is_final: Optional[bool] = False

class CorrectionResponse(BaseModel):
    user_sentence: str
    is_correct: bool
    corrected_german: str
    arabic_meaning: str
    why_summary: str
    replaced_words: List[ReplacementItem] = []
    radar_rules: List[RadarRule] = []
    source: str = "hybrid"

class ClipExample(BaseModel):
    de: str
    ar: str

class ClipCreate(BaseModel):
    text: str = Field(..., min_length=1)
    arabic_meaning: Optional[str] = ""
    label: Optional[str] = "جملة"
    grammar_notes: Optional[str] = ""
    examples: Optional[List[ClipExample]] = []

class ClipItem(BaseModel):
    id: str
    text: str
    arabic_meaning: str
    label: str
    grammar_notes: str
    examples: List[ClipExample] = []
    created_at: Optional[str] = ""

class TurnItem(BaseModel):
    id: str
    user_sentence: str
    is_correct: bool
    corrected_german: str
    arabic_meaning: str
    why_wrong: str
    replaced_words: List[ReplacementItem] = []
    radar_rules: List[RadarRule] = []
    created_at: Optional[str] = ""

class TurnCreate(BaseModel):
    user_sentence: str
    is_correct: bool
    corrected_german: str
    arabic_meaning: str
    why_wrong: Optional[str] = ""
    replaced_words: Optional[List[ReplacementItem]] = []
    radar_rules: Optional[List[RadarRule]] = []

class AiQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1)
    current_sentence: Optional[str] = ""

class AiQuestionResponse(BaseModel):
    answer_ar: str
    german_highlight: Optional[str] = ""
    examples: List[ClipExample] = []
