from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

from .content_models import CollectedContent, BlogArticle


class WorkflowStatus(str, Enum):
    """워크플로우 상태"""
    PENDING = "pending"
    COLLECTING = "collecting"
    WRITING = "writing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class BlogState(BaseModel):
    """LangGraph 워크플로우 상태"""

    # 입력 데이터
    topic: str = Field(..., description="블로그 주제")
    target_audience: str = Field(default="일반", description="타겟 독자층")
    tone: str = Field(default="친근하고 정보성", description="글의 톤앤매너")

    # 중간 처리 데이터
    collected_content: Optional[CollectedContent] = Field(default=None, description="수집된 콘텐츠")
    generated_article: Optional[BlogArticle] = Field(default=None, description="생성된 블로그 글")

    # 상태 정보
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING, description="현재 워크플로우 상태")
    current_step: str = Field(default="", description="현재 진행 중인 단계")
    progress_percentage: int = Field(default=0, ge=0, le=100, description="진행률 (0-100%)")

    # 에러 및 로그
    errors: list[str] = Field(default_factory=list, description="발생한 에러 목록")
    logs: list[str] = Field(default_factory=list, description="처리 로그")

    # 메타데이터
    started_at: Optional[str] = Field(default=None, description="작업 시작 시간")
    completed_at: Optional[str] = Field(default=None, description="작업 완료 시간")
    node_outputs: Dict[str, Any] = Field(default_factory=dict, description="각 노드의 출력 데이터")

    class Config:
        use_enum_values = True

    def add_log(self, message: str):
        """로그 메시지 추가"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def add_error(self, error_message: str):
        """에러 메시지 추가"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.errors.append(f"[{timestamp}] {error_message}")
        self.status = WorkflowStatus.FAILED

    def update_progress(self, step: str, percentage: int):
        """진행 상황 업데이트"""
        self.current_step = step
        self.progress_percentage = min(100, max(0, percentage))
        self.add_log(f"진행 상황 업데이트: {step} ({percentage}%)")

    def set_status(self, status: WorkflowStatus, step: str = ""):
        """상태 변경"""
        self.status = status
        if step:
            self.current_step = step
        self.add_log(f"상태 변경: {status.value}")

    def is_completed(self) -> bool:
        """작업 완료 여부 확인"""
        return self.status == WorkflowStatus.COMPLETED

    def is_failed(self) -> bool:
        """작업 실패 여부 확인"""
        return self.status == WorkflowStatus.FAILED

    def get_summary(self) -> Dict[str, Any]:
        """상태 요약 정보 반환"""
        return {
            "topic": self.topic,
            "status": self.status.value,
            "current_step": self.current_step,
            "progress": f"{self.progress_percentage}%",
            "sources_collected": self.collected_content.total_sources if self.collected_content else 0,
            "article_generated": bool(self.generated_article),
            "word_count": self.generated_article.word_count if self.generated_article else 0,
            "error_count": len(self.errors),
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }