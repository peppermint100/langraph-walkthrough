from typing import List, Dict, Optional
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from enum import Enum


class ContentType(str, Enum):
    BASIC_CONCEPT = "basic_concept"
    LATEST_TREND = "latest_trend"
    EXPERT_OPINION = "expert_opinion"


class SourceInfo(BaseModel):
    """수집된 소스 정보"""
    url: str = Field(..., description="원본 URL")
    title: str = Field(..., description="제목")
    summary: str = Field(..., description="요약 내용")
    content: str = Field(default="", description="전체 내용")
    credibility_score: float = Field(default=0.0, ge=0.0, le=1.0, description="신뢰도 점수 (0-1)")
    content_type: ContentType = Field(..., description="콘텐츠 타입")
    published_date: Optional[str] = Field(default=None, description="게시일")
    author: Optional[str] = Field(default=None, description="작성자")

    class Config:
        use_enum_values = True


class CollectedContent(BaseModel):
    """수집된 모든 콘텐츠"""
    topic: str = Field(..., description="검색 주제")
    basic_concepts: List[SourceInfo] = Field(default_factory=list, description="기본 개념 관련 정보")
    latest_trends: List[SourceInfo] = Field(default_factory=list, description="최신 트렌드 정보")
    expert_opinions: List[SourceInfo] = Field(default_factory=list, description="전문가 의견")
    collection_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="수집 시각")
    total_sources: int = Field(default=0, description="총 수집된 소스 수")

    def add_source(self, source: SourceInfo):
        """콘텐츠 타입에 따라 적절한 리스트에 소스 추가"""
        if source.content_type == ContentType.BASIC_CONCEPT:
            self.basic_concepts.append(source)
        elif source.content_type == ContentType.LATEST_TREND:
            self.latest_trends.append(source)
        elif source.content_type == ContentType.EXPERT_OPINION:
            self.expert_opinions.append(source)

        self.total_sources = len(self.basic_concepts + self.latest_trends + self.expert_opinions)

    def get_all_sources(self) -> List[SourceInfo]:
        """모든 소스를 하나의 리스트로 반환"""
        return self.basic_concepts + self.latest_trends + self.expert_opinions

    def get_sources_by_type(self, content_type: ContentType) -> List[SourceInfo]:
        """특정 타입의 소스만 반환"""
        if content_type == ContentType.BASIC_CONCEPT:
            return self.basic_concepts
        elif content_type == ContentType.LATEST_TREND:
            return self.latest_trends
        elif content_type == ContentType.EXPERT_OPINION:
            return self.expert_opinions
        return []


class BlogSection(BaseModel):
    """블로그 글의 각 섹션"""
    title: str = Field(..., description="섹션 제목")
    content: str = Field(..., description="섹션 내용")
    section_type: str = Field(..., description="섹션 타입 (intro, concept, trend, case, opinion, conclusion)")
    image_placeholder: Optional[str] = Field(default=None, description="이미지 삽입 위치 마커")


class BlogArticle(BaseModel):
    """완성된 블로그 글"""
    title: str = Field(..., description="블로그 제목")
    subtitle: Optional[str] = Field(default=None, description="부제목")
    content: str = Field(..., description="전체 내용 (마크다운 형식)")
    sections: List[BlogSection] = Field(default_factory=list, description="섹션별 내용")
    meta_tags: List[str] = Field(default_factory=list, description="메타 태그")
    keywords: List[str] = Field(default_factory=list, description="키워드")
    category: str = Field(default="일반", description="카테고리")
    estimated_read_time: int = Field(default=5, description="예상 읽기 시간 (분)")
    image_placeholders: List[str] = Field(default_factory=list, description="이미지 삽입 위치들")
    creation_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="생성 시각")
    word_count: int = Field(default=0, description="단어 수")

    def add_section(self, section: BlogSection):
        """섹션 추가"""
        self.sections.append(section)
        self.content += f"\n\n## {section.title}\n\n{section.content}"
        if section.image_placeholder:
            self.image_placeholders.append(section.image_placeholder)

    def calculate_word_count(self):
        """단어 수 계산"""
        # 한글과 영어 단어 수 계산 (간단한 구현)
        import re
        korean_chars = len(re.findall(r'[가-힣]', self.content))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', self.content))
        self.word_count = korean_chars + english_words

    def estimate_read_time(self):
        """읽기 시간 추정 (한국어 기준 분당 300자)"""
        if self.word_count == 0:
            self.calculate_word_count()
        self.estimated_read_time = max(1, self.word_count // 300)


class SearchQuery(BaseModel):
    """검색 쿼리 정보"""
    query: str = Field(..., description="검색어")
    content_type: ContentType = Field(..., description="검색할 콘텐츠 타입")
    language: str = Field(default="ko", description="검색 언어")
    max_results: int = Field(default=5, description="최대 결과 수")

    class Config:
        use_enum_values = True