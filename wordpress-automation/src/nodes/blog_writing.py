from typing import Dict, Any
from datetime import datetime
from loguru import logger

from ..models.state import BlogState, WorkflowStatus
from ..models.content_models import BlogArticle, BlogSection, CollectedContent


async def blog_writing_node(state: BlogState) -> Dict[str, Any]:
    """
    블로그 글 작성 노드 - 수집된 정보를 바탕으로 고품질 블로그 글 생성

    Args:
        state: 현재 워크플로우 상태

    Returns:
        업데이트된 상태 딕셔너리
    """

    logger.info(f"블로그 글 작성 시작: {state.topic}")

    try:
        # 전제 조건 확인
        if not state.collected_content:
            error_msg = "수집된 콘텐츠가 없습니다. 정보 수집을 먼저 실행해주세요."
            state.add_error(error_msg)
            logger.error(error_msg)
            return {"status": WorkflowStatus.FAILED, "errors": state.errors}

        # 상태 업데이트
        state.set_status(WorkflowStatus.WRITING, "LLM을 통한 블로그 글 작성")
        state.update_progress("블로그 글 작성 중", 10)

        # 수집된 콘텐츠 품질 검증
        content_quality = validate_content_for_writing(state.collected_content)
        if not content_quality["is_sufficient"]:
            logger.warning(f"콘텐츠 품질 경고: {content_quality['issues']}")
            state.add_log(f"콘텐츠 품질 경고: {', '.join(content_quality['issues'])}")

        state.update_progress("콘텐츠 품질 검증 완료", 20)

        # Perplexity로 블로그 글 작성
        from ..utils.perplexity_client import get_perplexity_client

        perplexity_client = get_perplexity_client()
        state.add_log("Perplexity를 통한 블로그 글 생성 시작")

        state.update_progress("블로그 글 작성 중", 30)

        # 수집된 정보를 요약하여 블로그 글 작성 프롬프트 생성
        content_summary = create_content_summary(state.collected_content)

        blog_writing_prompt = f"""
다음 정보를 바탕으로 '{state.topic}'에 대한 완성된 블로그 글을 한국어로 작성해주세요.

수집된 정보:
{content_summary}

요구사항:
1. 2000-3000자 분량의 완성된 블로그 글
2. 매력적인 제목과 구조화된 내용 (서론, 본론, 결론)
3. 독자가 {state.target_audience}이고 톤은 {state.tone}로 작성
4. 실용적이고 유익한 정보 제공
5. 자연스러운 한국어 문체

마크다운 형식으로 작성해주세요.
        """

        # Perplexity로 블로그 글 생성
        response = await perplexity_client.search(blog_writing_prompt, max_results=1)
        blog_content = response.content

        # BlogArticle 객체 생성
        blog_article = create_blog_article_from_content(blog_content, state.topic)

        state.update_progress("블로그 글 생성 완료", 70)

        # 생성된 글 품질 검증
        article_quality = validate_generated_article(blog_article)
        state.add_log(f"글 품질 점수: {article_quality['quality_score']:.2f}/1.0")

        if article_quality["quality_score"] < 0.5:
            logger.warning("생성된 글의 품질이 낮습니다")
            state.add_log("경고: 생성된 글의 품질이 기준 미달")

        state.update_progress("품질 검증 완료", 85)

        # 메타데이터 보완
        enhance_article_metadata(blog_article, state.collected_content)
        state.update_progress("메타데이터 보완 완료", 95)

        # 최종 상태 업데이트
        state.generated_article = blog_article
        state.node_outputs["blog_writing"] = {
            "title": blog_article.title,
            "word_count": blog_article.word_count,
            "estimated_read_time": blog_article.estimated_read_time,
            "sections_count": len(blog_article.sections),
            "image_placeholders_count": len(blog_article.image_placeholders),
            "meta_tags": blog_article.meta_tags,
            "keywords": blog_article.keywords,
            "category": blog_article.category,
            "quality_score": article_quality["quality_score"],
            "creation_timestamp": blog_article.creation_timestamp
        }

        state.update_progress("블로그 글 작성 완료", 100)
        state.add_log(f"블로그 글 작성 완료: '{blog_article.title}' ({blog_article.word_count}자)")

        logger.info(f"블로그 글 작성 완료: {blog_article.word_count}자, {len(blog_article.sections)}개 섹션")

        return {
            "generated_article": blog_article,
            "status": WorkflowStatus.REVIEWING,
            "current_step": "블로그 글 검토 대기",
            "progress_percentage": 100,
            "node_outputs": state.node_outputs
        }

    except Exception as e:
        error_msg = f"블로그 글 작성 중 오류 발생: {str(e)}"
        logger.error(error_msg)
        state.add_error(error_msg)

        return {
            "status": WorkflowStatus.FAILED,
            "errors": state.errors
        }


def validate_content_for_writing(collected_content) -> Dict[str, Any]:
    """
    글 작성을 위한 수집된 콘텐츠 충분성 검증

    Args:
        collected_content: 수집된 콘텐츠

    Returns:
        검증 결과
    """

    validation_result = {
        "is_sufficient": True,
        "issues": [],
        "recommendations": []
    }

    # 최소 소스 수 확인
    if collected_content.total_sources < 3:
        validation_result["is_sufficient"] = False
        validation_result["issues"].append(f"소스 수 부족: {collected_content.total_sources}개")
        validation_result["recommendations"].append("최소 3개 이상의 소스 필요")

    # 콘텐츠 다양성 확인
    content_types_count = sum([
        len(collected_content.basic_concepts) > 0,
        len(collected_content.latest_trends) > 0,
        len(collected_content.practical_cases) > 0,
        len(collected_content.expert_opinions) > 0
    ])

    if content_types_count < 2:
        validation_result["issues"].append("콘텐츠 타입 다양성 부족")
        validation_result["recommendations"].append("최소 2개 이상의 콘텐츠 타입 필요")

    # 콘텐츠 품질 확인
    all_sources = collected_content.get_all_sources()
    avg_credibility = sum(source.credibility_score for source in all_sources) / len(all_sources) if all_sources else 0

    if avg_credibility < 0.4:
        validation_result["issues"].append(f"평균 신뢰도 낮음: {avg_credibility:.2f}")
        validation_result["recommendations"].append("더 신뢰할 수 있는 소스 필요")

    # 콘텐츠 양 확인
    total_content_length = sum(len(source.summary) + len(source.content) for source in all_sources)
    if total_content_length < 500:
        validation_result["issues"].append("수집된 콘텐츠 양 부족")
        validation_result["recommendations"].append("더 많은 정보 수집 필요")

    return validation_result


def validate_generated_article(article: BlogArticle) -> Dict[str, Any]:
    """
    생성된 블로그 글의 품질 검증

    Args:
        article: 생성된 블로그 글

    Returns:
        품질 평가 결과
    """

    quality_factors = {}

    # 길이 적절성 (1000-4000자 사이가 적정)
    word_count = article.word_count
    if 1000 <= word_count <= 4000:
        quality_factors["length"] = 1.0
    elif 500 <= word_count < 1000 or 4000 < word_count <= 6000:
        quality_factors["length"] = 0.7
    else:
        quality_factors["length"] = 0.3

    # 구조 완성도 (섹션 수, 제목 품질)
    sections_count = len(article.sections)
    if 3 <= sections_count <= 7:
        quality_factors["structure"] = 1.0
    elif 2 <= sections_count < 3 or 7 < sections_count <= 10:
        quality_factors["structure"] = 0.7
    else:
        quality_factors["structure"] = 0.3

    # 메타데이터 완성도
    metadata_score = 0
    if article.title and len(article.title) > 5:
        metadata_score += 0.3
    if article.meta_tags and len(article.meta_tags) >= 3:
        metadata_score += 0.3
    if article.keywords and len(article.keywords) >= 3:
        metadata_score += 0.2
    if article.category:
        metadata_score += 0.2

    quality_factors["metadata"] = min(1.0, metadata_score)

    # 이미지 플레이스홀더 적절성
    image_count = len(article.image_placeholders)
    expected_images = max(1, sections_count // 2)
    if image_count >= expected_images:
        quality_factors["images"] = 1.0
    elif image_count > 0:
        quality_factors["images"] = 0.6
    else:
        quality_factors["images"] = 0.2

    # 전체 품질 점수 계산
    overall_quality = sum(quality_factors.values()) / len(quality_factors)

    return {
        "quality_score": overall_quality,
        "factors": quality_factors,
        "word_count": word_count,
        "sections_count": sections_count,
        "has_images": image_count > 0,
        "recommendations": generate_quality_recommendations(quality_factors)
    }


def enhance_article_metadata(article: BlogArticle, collected_content) -> None:
    """
    수집된 콘텐츠를 바탕으로 블로그 글의 메타데이터 보완

    Args:
        article: 보완할 블로그 글
        collected_content: 수집된 콘텐츠
    """

    # 키워드 보완 (수집된 소스에서 중요 키워드 추출)
    all_sources = collected_content.get_all_sources()
    common_terms = extract_common_terms([source.title + " " + source.summary for source in all_sources])

    # 기존 키워드와 중복되지 않는 새로운 키워드 추가
    new_keywords = [term for term in common_terms[:5] if term not in article.keywords]
    article.keywords.extend(new_keywords[:3])

    # 메타 태그 보완
    if len(article.meta_tags) < 5:
        additional_tags = [collected_content.topic] + new_keywords
        for tag in additional_tags:
            if tag not in article.meta_tags and len(article.meta_tags) < 8:
                article.meta_tags.append(tag)

    # 카테고리 자동 분류
    if article.category == "일반":
        article.category = classify_category(collected_content.topic, all_sources)


def extract_common_terms(texts: list) -> list:
    """텍스트에서 공통으로 나타나는 중요 용어 추출"""
    import re
    from collections import Counter

    # 간단한 키워드 추출 (실제로는 더 정교한 NLP 기법 사용 가능)
    all_words = []
    for text in texts:
        # 한글 단어 추출 (2글자 이상)
        korean_words = re.findall(r'[가-힣]{2,}', text)
        all_words.extend(korean_words)

    # 빈도수 기반 상위 키워드 반환
    word_counts = Counter(all_words)
    return [word for word, count in word_counts.most_common(10) if count >= 2]


def classify_category(topic: str, sources: list) -> str:
    """주제와 소스를 바탕으로 카테고리 자동 분류"""

    category_keywords = {
        "기술": ["AI", "인공지능", "프로그래밍", "개발", "코딩", "소프트웨어", "기술", "IT"],
        "비즈니스": ["비즈니스", "경영", "마케팅", "스타트업", "창업", "투자", "경제"],
        "라이프스타일": ["건강", "운동", "요리", "여행", "취미", "생활", "패션"],
        "교육": ["교육", "학습", "공부", "강의", "수업", "교사", "학생"],
        "엔터테인먼트": ["게임", "영화", "음악", "드라마", "예술", "문화"]
    }

    topic_lower = topic.lower()
    source_text = " ".join([source.title + " " + source.summary for source in sources]).lower()

    category_scores = {}
    for category, keywords in category_keywords.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in topic_lower:
                score += 3
            if keyword.lower() in source_text:
                score += 1
        category_scores[category] = score

    # 점수가 가장 높은 카테고리 반환
    best_category = max(category_scores, key=category_scores.get)
    return best_category if category_scores[best_category] > 0 else "일반"


def generate_quality_recommendations(quality_factors: Dict[str, float]) -> list:
    """품질 점수를 바탕으로 개선 권장사항 생성"""

    recommendations = []

    if quality_factors.get("length", 1.0) < 0.7:
        recommendations.append("글 길이를 1000-4000자 사이로 조정 권장")

    if quality_factors.get("structure", 1.0) < 0.7:
        recommendations.append("섹션 구조를 3-7개 사이로 재구성 권장")

    if quality_factors.get("metadata", 1.0) < 0.7:
        recommendations.append("메타태그와 키워드 보완 필요")

    if quality_factors.get("images", 1.0) < 0.7:
        recommendations.append("이미지 플레이스홀더 추가 권장")

    return recommendations


def create_content_summary(collected_content: CollectedContent) -> str:
    """수집된 콘텐츠를 요약 문자열로 변환"""
    summary = f"주제: {collected_content.topic}\n\n"

    if collected_content.basic_concepts:
        summary += "== 기본 개념 ==\n"
        for source in collected_content.basic_concepts[:3]:
            summary += f"- {source.title}: {source.summary}\n"
        summary += "\n"

    if collected_content.latest_trends:
        summary += "== 최신 트렌드 ==\n"
        for source in collected_content.latest_trends[:3]:
            summary += f"- {source.title}: {source.summary}\n"
        summary += "\n"

    if collected_content.practical_cases:
        summary += "== 실무 활용 사례 ==\n"
        for source in collected_content.practical_cases[:3]:
            summary += f"- {source.title}: {source.summary}\n"
        summary += "\n"

    if collected_content.expert_opinions:
        summary += "== 전문가 의견 ==\n"
        for source in collected_content.expert_opinions[:3]:
            summary += f"- {source.title}: {source.summary}\n"
        summary += "\n"

    return summary


def create_blog_article_from_content(content: str, topic: str) -> BlogArticle:
    """Perplexity 응답에서 BlogArticle 객체 생성"""

    # 제목 추출 (첫 번째 # 제목 또는 기본 제목)
    lines = content.split('\n')
    title = f"{topic}에 대한 완전 가이드"

    for line in lines:
        if line.strip().startswith('# '):
            title = line.strip()[2:].strip()
            break

    # 섹션들 생성 (간단한 구현)
    sections = []
    current_section = None
    section_content = ""

    for line in lines:
        if line.strip().startswith('## '):
            # 이전 섹션 저장
            if current_section:
                sections.append(BlogSection(
                    title=current_section,
                    content=section_content.strip(),
                    section_type="general"
                ))
            # 새 섹션 시작
            current_section = line.strip()[3:].strip()
            section_content = ""
        else:
            section_content += line + '\n'

    # 마지막 섹션 저장
    if current_section:
        sections.append(BlogSection(
            title=current_section,
            content=section_content.strip(),
            section_type="general"
        ))

    # 기본 메타데이터 생성
    keywords = [topic]
    if '한의원' in topic:
        keywords.extend(['한의원', '한방치료', '건강'])

    # BlogArticle 객체 생성
    article = BlogArticle(
        title=title,
        content=content,
        sections=sections,
        meta_tags=keywords[:5],
        keywords=keywords[:10],
        category=classify_category_simple(topic)
    )

    # 단어 수 및 읽기 시간 계산
    article.calculate_word_count()
    article.estimate_read_time()

    return article


def classify_category_simple(topic: str) -> str:
    """간단한 카테고리 분류"""
    topic_lower = topic.lower()

    if any(word in topic_lower for word in ['한의원', '의료', '건강', '치료']):
        return '건강'
    elif any(word in topic_lower for word in ['기술', '개발', 'ai', '프로그래밍']):
        return '기술'
    elif any(word in topic_lower for word in ['비즈니스', '마케팅', '창업']):
        return '비즈니스'
    else:
        return '일반'